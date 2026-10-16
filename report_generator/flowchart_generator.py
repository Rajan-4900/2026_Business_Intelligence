"""
Flowcharts rendered as inline SVG (no Graphviz/Mermaid binaries needed;
WeasyPrint draws SVG natively).

Diagrams A, B and D describe the platform's actual pipeline as implemented
(business_intelligence/analysis.py and prediction_engine/). Diagrams C and E
are recommended manual processes and are captioned as such in the PDF.
"""
from xml.sax.saxutils import escape

from . import theme
from .content import nice

FONT = f"{theme.BODY_FONT}, DejaVu Sans, sans-serif"
LABEL_FONT = f"{theme.MONO_FONT}, {theme.BODY_FONT}, DejaVu Sans, monospace"
BOX_W = 310
BOX_X = 20
NOTE_X = BOX_X + BOX_W + 18
VIEW_W = 580
LINE_H = 16
NOTE_LINE_H = 13.5
GAP = 14

STYLES = theme.FLOW  # light fills, coloured outlines (see theme.py)


def _wrap(text, max_chars):
    words, lines, cur = str(text).split(), [], ''
    for w in words:
        if len(cur) + len(w) + (1 if cur else 0) <= max_chars:
            cur = f'{cur} {w}'.strip()
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines or ['']


def _arrow(x1, y1, x2, y2):
    """Line plus a filled arrowhead (polygon; avoids SVG <marker>)."""
    out = [f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2 - 6}" stroke="{theme.ACCENT}" stroke-width="1.2"/>']
    out.append(f'<polygon points="{x2 - 5},{y2 - 7} {x2 + 5},{y2 - 7} {x2},{y2}" fill="{theme.ACCENT}"/>')
    return out


def _text_lines(lines, x, y, size, weight='normal', color=theme.TEXT, anchor='start', line_h=LINE_H,
                font=FONT):
    out = []
    for i, line in enumerate(lines):
        out.append(f'<text x="{x}" y="{y + i * line_h}" font-family="{font}" font-size="{size}" '
                   f'font-weight="{weight}" fill="{color}" text-anchor="{anchor}">{escape(line)}</text>')
    return out


def flowchart(steps, branches=None):
    """
    steps: [{'text', 'note' (optional), 'kind'}] drawn top-to-bottom.
    branches: optional [(label, text, kind), (label, text, kind)] drawn
    side by side below the last step (used for the Go/No-Go outcome).
    """
    parts = []
    y = 10
    centre = BOX_X + BOX_W / 2
    prev_bottom = None
    for step in steps:
        lines = _wrap(step['text'], 38)
        note_lines = _wrap(step.get('note', ''), 30) if step.get('note') else []
        h = max(26, 12 + LINE_H * len(lines), 8 + NOTE_LINE_H * len(note_lines))
        fill, stroke = STYLES[step.get('kind', 'process')]
        if prev_bottom is not None:
            parts += _arrow(centre, prev_bottom, centre, y)
        if step.get('kind') == 'decision':
            parts.append(f'<polygon points="{centre},{y} {BOX_X + BOX_W},{y + h / 2} {centre},{y + h} {BOX_X},{y + h / 2}" '
                         f'fill="{fill}" stroke="{stroke}" stroke-width="1.2"/>')
        else:
            parts.append(f'<rect x="{BOX_X}" y="{y}" width="{BOX_W}" height="{h}" rx="4" fill="{fill}" '
                         f'stroke="{stroke}" stroke-width="1.2"/>')
        text_y = y + h / 2 - (len(lines) - 1) * LINE_H / 2 + 4
        parts += _text_lines(lines, centre, text_y, 13, 'bold' if step.get('kind') in ('start', 'output') else 'normal',
                             anchor='middle')
        if note_lines:
            note_y = y + h / 2 - (len(note_lines) - 1) * NOTE_LINE_H / 2 + 3
            parts += _text_lines(note_lines, NOTE_X, note_y, 10, color=theme.MUTED, line_h=NOTE_LINE_H,
                                  font=LABEL_FONT)
        prev_bottom = y + h
        y += h + GAP

    if branches:
        bw = BOX_W / 2 - 8
        bottom = prev_bottom
        top = y + 8
        for i, (label, text, kind) in enumerate(branches):
            bx = BOX_X + i * (bw + 16)
            lines = _wrap(text, 20)
            h = 14 + LINE_H * len(lines)
            fill, stroke = STYLES[kind]
            parts.append(f'<polyline points="{centre},{bottom} {centre},{bottom + 12} {bx + bw / 2},{bottom + 12} '
                         f'{bx + bw / 2},{top - 6}" fill="none" stroke="{theme.ACCENT}" stroke-width="1.2"/>')
            parts.append(f'<polygon points="{bx + bw / 2 - 5},{top - 7} {bx + bw / 2 + 5},{top - 7} {bx + bw / 2},{top}" '
                         f'fill="{theme.ACCENT}"/>')
            parts += _text_lines([label], bx + bw / 2 + (8 if i else -8), bottom + 26, 10.5, 'normal', theme.ACCENT,
                                 anchor='start' if i else 'end', font=LABEL_FONT)
            parts.append(f'<rect x="{bx}" y="{top}" width="{bw}" height="{h}" rx="4" fill="{fill}" stroke="{stroke}" '
                         f'stroke-width="1.2"/>')
            parts += _text_lines(lines, bx + bw / 2, top + h / 2 - (len(lines) - 1) * LINE_H / 2 + 4, 12,
                                 anchor='middle')
            y = max(y, top + h + 10)
    height = y
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {VIEW_W} {height}" '
            'role="img">' + ''.join(parts) + '</svg>')


def build_all(snapshot):
    heat = snapshot.get('heatmap') or {}
    rec = snapshot.get('recommendation') or {}
    rev = snapshot.get('revenue') or {}
    target = nice(snapshot.get('target_business')) or 'the target business'
    radius = snapshot['location']['radius_m']

    a = flowchart([
        {'text': 'Location selected on the map', 'kind': 'start',
         'note': f"{snapshot['location']['latitude']:.5f}, {snapshot['location']['longitude']:.5f}"},
        {'text': 'Collect mapped features from OpenStreetMap',
         'note': f'Overpass API, {radius:,} m radius: shops, amenities, buildings, roads, transit'},
        {'text': 'Summarise points of interest', 'note': 'Counts by category; competitor matching'},
        {'text': 'Classify 9 sectors by feature count', 'kind': 'model',
         'note': '3 rings x 3 wedges. High 15+, Medium 5–14, Low 1–4'},
        {'text': 'ML business recommendation', 'kind': 'model', 'note': 'Decision tree on intensity + area type'},
        {'text': 'Feasibility rules (Go / No-Go)', 'kind': 'output',
         'note': 'Dataset list, model match, or 2+ similar places nearby'},
    ])

    b = flowchart([
        {'text': 'Sector counts from the heatmap', 'kind': 'start',
         'note': f"This location: {heat.get('counts', {}).get('high', 0)} High, "
                 f"{heat.get('counts', {}).get('medium', 0)} Medium, {heat.get('counts', {}).get('low', 0)} Low"},
        {'text': 'Dominant intensity = High if any sector is High, else Medium if any is Medium, else Low',
         'note': f"Result: {heat.get('dominant', 'unknown')}"},
        {'text': 'Infer area type from nearby amenity tags',
         'note': f"Result: {rec.get('area_hint') or 'no clear type (default variant used)'}"},
        {'text': 'Map to a (shops, area) example from the training data',
         'note': 'Fixed lookup per intensity level'},
        {'text': 'Decision tree predicts one business label', 'kind': 'model',
         'note': '72 labelled training rows; outputs a label, not a score'},
        {'text': 'Alternatives = predictions for the other intensity levels', 'kind': 'output',
         'note': f"Primary: {nice(rec.get('primary')) or 'n/a'}"},
    ])

    c = flowchart([
        {'text': 'Validate demand on site', 'kind': 'start', 'note': 'Footfall counts, short survey'},
        {'text': 'Research competitors', 'note': 'Visit the places listed in this report'},
        {'text': 'Estimate start-up cost', 'note': 'Written quotes'},
        {'text': 'Write the business plan', 'note': 'Compare costs with revenue scenarios'},
        {'text': 'Verify licences and legal requirements', 'note': 'With the relevant authorities'},
        {'text': 'Set up premises, suppliers and staff'},
        {'text': 'Launch', 'kind': 'output', 'note': 'Soft launch first'},
        {'text': 'Monitor performance and adjust', 'note': 'Compare actual sales with forecast'},
    ])

    assumptions = rev.get('assumptions') or {}
    d = flowchart([
        {'text': 'Mapped features around the location', 'kind': 'start', 'note': 'OpenStreetMap, 2 km'},
        {'text': 'Visitor proxy and area scores', 'kind': 'model',
         'note': 'Distance-weighted counts of homes, offices, transit, attractions (not measured footfall)'},
        {'text': 'Huff model: share of local demand', 'kind': 'model',
         'note': 'Attractiveness vs. distance to competitors'},
        {'text': 'Extended Huff: competition adjustment', 'kind': 'model',
         'note': 'Reduces demand for each additional competitor'},
        {'text': 'Customers x average spend', 'kind': 'model',
         'note': (f"Engine assumptions for {target}: spend ₹{assumptions.get('avg_spend', 0):,.0f}, "
                  f"conversion {assumptions.get('conversion_rate', 0) * 100:.0f}%") if assumptions else
                 'Engine assumptions unavailable'},
        {'text': 'Daily gross sales  →  x30 monthly, x365 annual', 'kind': 'output'},
        {'text': 'Scenario range from confidence score', 'kind': 'output',
         'note': 'Conservative / base / optimistic (±10–40%)'},
    ])

    e = flowchart([
        {'text': 'Platform location analysis (this report)', 'kind': 'start'},
        {'text': 'Validate demand yourself', 'note': 'Count real customers at peak and off-peak times'},
        {'text': 'Assess competition in person'},
        {'text': 'Estimate start-up and monthly costs', 'note': 'Not available in the platform data'},
        {'text': 'Assess risks (see risk matrix)'},
        {'text': 'Does the plan work under the conservative scenario?', 'kind': 'decision'},
    ], branches=[
        ('No / unsure', 'Collect more evidence before investing', 'warn'),
        ('Yes', 'Proceed to detailed business planning', 'output'),
    ])
    return {'analysis': a, 'recommendation': b, 'implementation': c, 'revenue': d, 'go_no_go': e}
