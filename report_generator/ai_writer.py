"""
Writes the report's explanatory text.

Each of the five stages asks Gemini (reusing the project's GEMINI_API_KEY /
GEMINI_MODEL_NAME configuration from tracker.ai.gemini_service) for JSON,
then checks it against the stage schema and rejects any figure that is not
in the evidence. A stage that fails for any reason falls back to the
deterministic text in content.py, and the PDF labels which text is which.
"""
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from django.conf import settings

from tracker.ai.gemini_service import _get_gemini_config
from tracker.ai.validators import sanitize_context_for_ai

from . import content
from .prompts import MONEY_ONLY_STAGES, REPORT_SYSTEM_PROMPT, STAGE_SCHEMAS, build_stage_prompt
from .validators import ValidationError, collect_numbers, ungrounded_numbers, validate_ai_payload

logger = logging.getLogger(__name__)

STAGES = ('location', 'heatmap_recs', 'revenue', 'roadmap', 'summary')


class AIUnavailable(Exception):
    pass


def build_evidence(snapshot, risks):
    """Compact, AI-safe view of the snapshot (no raw point lists)."""
    pois = snapshot.get('pois') or {}
    heat = snapshot.get('heatmap') or {}
    rev = dict(snapshot.get('revenue') or {})
    rev.pop('excluded_proxy_fields', None)
    comp = dict(snapshot.get('competition') or {})
    comp['list'] = (comp.get('list') or [])[:8]
    feas = dict(snapshot.get('feasibility') or {})
    if isinstance(feas.get('evidence'), dict):
        feas['evidence'] = {k: v for k, v in feas['evidence'].items() if k != 'allowed_businesses'}
    evidence = {
        'location': snapshot['location'],
        'target_business': snapshot.get('target_business'),
        'requested_business': snapshot.get('requested_business'),
        'pois': {k: pois.get(k) for k in ('in_radius', 'named', 'by_family', 'top_types')},
        'heatmap': {k: heat.get(k) for k in ('dominant', 'counts', 'thresholds', 'placeholder_used')},
        'heatmap_sectors': [{k: s[k] for k in ('ring', 'wedge', 'count', 'intensity')} for s in heat.get('sectors', [])],
        'recommendation': {k: v for k, v in (snapshot.get('recommendation') or {}).items() if k != 'choices'},
        'candidates': snapshot.get('candidates') or [],
        'revenue': rev,
        'competition': comp,
        'feasibility': feas,
        'risks': [{k: r[k] for k in ('risk', 'likelihood', 'impact', 'basis', 'evidence')} for r in risks],
        'missing_data': snapshot.get('missing') or [],
    }
    return sanitize_context_for_ai(evidence)


def _call_gemini(prompt):
    if not getattr(settings, 'REPORT_AI_ENABLED', True):
        raise AIUnavailable('AI commentary is disabled (REPORT_AI_ENABLED=False).')
    api_key, model_name = _get_gemini_config()
    if not api_key:
        raise AIUnavailable('GEMINI_API_KEY is not configured.')
    import google.generativeai as genai
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(
        model_name=model_name,
        system_instruction=REPORT_SYSTEM_PROMPT,
        generation_config={'response_mime_type': 'application/json', 'temperature': 0.2},
    )
    response = model.generate_content(prompt, request_options={'timeout': settings.REPORT_AI_TIMEOUT})
    text = (getattr(response, 'text', '') or '').strip()
    if not text:
        raise ValidationError('Gemini returned an empty response', 'ai_invalid')
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        raise ValidationError('Gemini did not return valid JSON', 'ai_invalid')


def _strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _strings(v)


def _run_stage(stage, evidence, evidence_numbers, candidate_names):
    raw = _call_gemini(build_stage_prompt(stage, evidence))
    clean = validate_ai_payload(raw, STAGE_SCHEMAS[stage])
    if stage == 'heatmap_recs':
        clean['recommendations'] = [r for r in clean['recommendations']
                                    if r['business'].strip().lower() in candidate_names]
    if stage == 'roadmap' and len(clean['steps']) < 5:
        raise ValidationError('AI roadmap has too few steps', 'ai_invalid')
    bad = []
    for text in _strings(clean):
        bad.extend(ungrounded_numbers(text, evidence_numbers, money_only=stage in MONEY_ONLY_STAGES))
    if bad:
        raise ValidationError(f'AI text contained figures not in the analysis: {", ".join(bad[:5])}', 'ai_ungrounded')
    return clean


def _fallback(stage, snapshot, risks):
    if stage == 'location':
        return content.location_text(snapshot)
    if stage == 'heatmap_recs':
        data = content.heatmap_text(snapshot)
        data['recommendations'] = [content.candidate_text(snapshot, c) for c in snapshot.get('candidates') or []]
        return data
    if stage == 'revenue':
        return content.revenue_text(snapshot)
    if stage == 'roadmap':
        return {'steps': content.default_roadmap(snapshot.get('target_business'))['steps']}
    return content.summary_text(snapshot, risks)


def write_report_text(snapshot, risks):
    """
    Returns {'stages': {stage: {'data', 'source': 'ai'|'template', 'note'}},
             'ai_status': 'used'|'partial'|'unavailable', 'ai_message': str}.
    """
    evidence = build_evidence(snapshot, risks)
    evidence_numbers = collect_numbers(evidence) | collect_numbers(
        [_fallback(st, snapshot, risks) for st in STAGES]) | {float(datetime.now().year)}
    candidate_names = {c['business'].strip().lower() for c in snapshot.get('candidates') or []}

    def attempt(stage):
        try:
            return stage, _run_stage(stage, evidence, evidence_numbers, candidate_names), ''
        except AIUnavailable as exc:
            return stage, None, str(exc)
        except ValidationError as exc:
            logger.warning('Report AI stage %s rejected: %s', stage, exc)
            return stage, None, str(exc)
        except Exception as exc:  # network, quota, SDK errors
            logger.warning('Report AI stage %s failed: %s', stage, exc)
            return stage, None, f'Gemini request failed ({type(exc).__name__}).'

    with ThreadPoolExecutor(max_workers=len(STAGES)) as pool:
        results = list(pool.map(attempt, STAGES))

    stages = {}
    for stage, data, note in results:
        if data is not None:
            fallback_recs = None
            if stage == 'heatmap_recs':
                # Candidates the AI skipped still get the template explanation.
                covered = {r['business'].strip().lower() for r in data['recommendations']}
                fallback_recs = [content.candidate_text(snapshot, c) for c in snapshot.get('candidates') or []
                                 if c['business'].strip().lower() not in covered]
                data['recommendations'].extend(fallback_recs)
            stages[stage] = {'data': data, 'source': 'ai', 'note': ''}
        else:
            stages[stage] = {'data': _fallback(stage, snapshot, risks), 'source': 'template', 'note': note}

    used = sum(1 for s in stages.values() if s['source'] == 'ai')
    if used == len(STAGES):
        status, message = 'used', 'Explanations were written by Google Gemini from the analysis data and checked for unsupported figures.'
    elif used:
        status, message = 'partial', (f'{used} of {len(STAGES)} sections were written by Google Gemini; the others use '
                                      'template text because the AI output was unavailable or failed validation.')
    else:
        reasons = sorted({s['note'] for s in stages.values() if s['note']})
        status, message = 'unavailable', ('AI-generated commentary was unavailable, so this report uses template '
                                          'explanations built directly from the analysis data. '
                                          + (f'Reason: {reasons[0]}' if reasons else ''))
    return {'stages': stages, 'ai_status': status, 'ai_message': message.strip()}
