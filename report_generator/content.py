"""
Deterministic report text, business-specific roadmaps and the risk register.

These are used on their own when Gemini is unavailable and as the baseline
the AI text is checked against. Every sentence is built from the snapshot,
so nothing here can introduce a number the analysis did not produce.
"""
import re

# ---------------------------------------------------------------------------
# Formatting helpers (also registered as template filters)
# ---------------------------------------------------------------------------


def inr(amount):
    """Indian digit grouping: 1234567.8 -> '₹12,34,568'."""
    if amount is None:
        return '—'
    value = int(round(float(amount)))
    sign = '-' if value < 0 else ''
    digits = str(abs(value))
    if len(digits) > 3:
        head, tail = digits[:-3], digits[-3:]
        head = re.sub(r'(\d)(?=(\d{2})+$)', r'\1,', head)
        digits = f'{head},{tail}'
    return f'{sign}₹{digits}'


def nice(name):
    """'fast_food' -> 'Fast Food'; words already in capitals (ATM) are kept."""
    words = (name or '').replace('_', ' ').split()
    return ' '.join(w if w.isupper() else w.capitalize() for w in words)


def pct(fraction, digits=0):
    return f'{float(fraction) * 100:.{digits}f}%'


# ---------------------------------------------------------------------------
# Business categories -> roadmap templates
# ---------------------------------------------------------------------------

GROUP_KEYWORDS = [
    ('health', ('pharmacy', 'medical', 'chemist', 'optical', 'clinic', 'diagnostic', 'dental')),
    ('food', ('cafe', 'coffee', 'restaurant', 'fast food', 'food', 'bakery', 'juice', 'ice cream', 'sweet',
              'tiffin', 'tea', 'canteen', 'dhaba')),
    ('industrial', ('warehouse', 'storage', 'logistics', 'cold storage', 'farm', 'timber', 'scrap', 'fabrication')),
    ('education', ('coaching', 'tuition', 'training', 'academy')),
    ('services', ('atm', 'repair', 'salon', 'gym', 'laundry', 'courier', 'printing', 'photocopy', 'tailor',
                  'travel', 'internet', 'cinema', 'fuel', 'spa')),
    ('retail', ('shop', 'store', 'mart', 'supermarket', 'grocery', 'boutique', 'booth', 'wholesale', 'dealer',
                'supply')),
]

GROUP_LABELS = {
    'food': 'food & beverage', 'retail': 'retail', 'health': 'healthcare retail',
    'services': 'local service', 'education': 'education', 'industrial': 'storage / industrial',
    'general': 'general',
}


def business_group(name):
    lower = (name or '').lower().replace('_', ' ')
    for group, words in GROUP_KEYWORDS:
        if any(w in lower for w in words):
            return group
    return 'general'


# Steps shared by every group; group-specific wording is merged in below.
# 'weeks' are planning estimates only and are labelled as such in the PDF.
_BASE_STEPS = [
    ('validate_demand', 'Validate local customer demand', 2),
    ('competitors', 'Study nearby competitors in person', 1),
    ('capital', 'Estimate start-up capital', 2),
    ('costs', 'Get real rent and operating cost quotes', 2),
    ('plan', 'Write a simple business plan', 2),
    ('legal', 'Verify licences and legal requirements', 4),
    ('suppliers', 'Line up suppliers and staff', 3),
    ('premises', 'Prepare the premises', 4),
    ('launch', 'Soft launch, then open fully', 2),
    ('monitor', 'Track sales and adjust', 8),
]

_GROUP_DETAILS = {
    'food': {
        'validate_demand': ['Count people passing the shortlisted frontage at breakfast, lunch and evening on a weekday and a weekend',
                            'Ask 30–50 passers-by what they buy nearby, how often and at what price'],
        'competitors': ['Visit the nearest outlets listed in this report at peak hours; note queue length, menu prices and seating',
                        'Check their delivery-app ratings and opening hours'],
        'capital': ['List kitchen equipment, furniture, fit-out, first stock and deposit',
                    'Get at least two written quotes for each large item'],
        'legal': ['Check the FSSAI registration or licence category that applies to your turnover and format',
                  'Ask the local municipal office about the trade licence, signage and fire-safety requirements',
                  'Confirm GST registration needs with a chartered accountant'],
        'suppliers': ['Shortlist suppliers for core ingredients and packaging', 'Plan kitchen and service staff for peak hours'],
        'premises': ['Confirm water, drainage, ventilation/exhaust and electrical load for cooking'],
    },
    'retail': {
        'validate_demand': ['Count walk-in traffic at the shortlisted shopfront at different times',
                            'Ask nearby residents and workers which products they cannot find locally'],
        'competitors': ['Visit the competitors listed in this report; compare range, prices and stock depth'],
        'capital': ['Estimate opening stock, shelving, billing system and fit-out with written quotes'],
        'legal': ['Ask the municipal office about the shops & establishments registration and trade licence',
                  'Confirm GST registration needs with a chartered accountant'],
        'suppliers': ['Compare distributor terms (credit days, minimum order, returns)'],
        'premises': ['Check frontage visibility, loading access and storage space'],
    },
    'health': {
        'validate_demand': ['Map nearby clinics, hospitals and residential blocks that would generate prescriptions',
                            'Talk to local doctors about unmet needs (late hours, home delivery)'],
        'competitors': ['Visit nearby pharmacies; note opening hours, delivery and stock availability'],
        'capital': ['Estimate stock, refrigeration, shelving and billing software'],
        'legal': ['Verify the drug licence requirements with the State Drug Control department',
                  'Confirm the qualified pharmacist requirement and shop registration',
                  'Confirm GST registration needs with a chartered accountant'],
        'suppliers': ['Shortlist licensed distributors and agree credit terms'],
        'premises': ['Confirm space and storage conditions required by the licensing authority'],
    },
    'services': {
        'validate_demand': ['Identify who would use the service (residents, offices, vehicles, students) and estimate how many are nearby',
                            'Run a short survey or pre-booking test before committing to premises'],
        'competitors': ['Visit or call nearby providers; compare prices, waiting times and reviews'],
        'capital': ['List equipment, fit-out, tools and any franchise or partner fees'],
        'legal': ['Check trade licence and any service-specific permits with the municipal office',
                  'If the business is operated through a partner (e.g. an ATM operator or fuel company), confirm their site criteria first'],
        'suppliers': ['Line up equipment vendors, consumables and trained staff'],
        'premises': ['Check power, water, access and parking needs of the service'],
    },
    'education': {
        'validate_demand': ['Count schools and colleges nearby and talk to parents/students about subjects and fees'],
        'competitors': ['Compare nearby centres: subjects, batch sizes, fees and results claims'],
        'capital': ['Estimate classroom fit-out, furniture, teaching aids and marketing'],
        'legal': ['Ask the municipal office about trade licence, building use and fire-safety rules'],
        'suppliers': ['Recruit and trial teachers before launch'],
        'premises': ['Check classroom size, ventilation, toilets and safe access'],
    },
    'industrial': {
        'validate_demand': ['Identify likely customers (traders, manufacturers, e-commerce sellers) and get letters of intent'],
        'competitors': ['Compare nearby facilities on rates, capacity and services'],
        'capital': ['Estimate land/building, racking, handling equipment and security'],
        'legal': ['Check land-use/zoning, fire NOC and any pollution-control requirements with the relevant authorities'],
        'suppliers': ['Arrange transport partners and staffing'],
        'premises': ['Confirm truck access, road width, load-bearing floors and power'],
    },
    'general': {
        'validate_demand': ['Describe your target customer and estimate how many live or work within 2 km',
                            'Test interest with a small survey or pre-orders'],
        'competitors': ['Visit similar businesses nearby and note prices and quality'],
        'capital': ['List all one-time costs with written quotes'],
        'legal': ['Ask the municipal office which registrations apply to your activity',
                  'Confirm GST registration needs with a chartered accountant'],
        'suppliers': ['Shortlist suppliers and staff'],
        'premises': ['Check the premises suits the activity (power, water, access)'],
    },
}

_COMMON_DETAILS = {
    'costs': ['Collect rent quotes for 2–3 premises in the high-activity sectors of this report',
              'Estimate monthly salaries, utilities, maintenance and marketing'],
    'plan': ['Compare the revenue scenarios in this report against your monthly cost estimate',
             'Decide the minimum monthly sales you need to break even'],
    'launch': ['Open with a limited offering to test operations', 'Collect customer feedback daily during the first weeks'],
    'monitor': ['Record daily sales and customer counts', 'Compare actual sales with the forecast scenarios and adjust pricing or hours'],
}

_STEP_META = {
    'validate_demand': ('Confirm that enough customers want this business here.',
                        'Survey notes and footfall counts', 'A go/no-go view on demand based on your own observations',
                        'The report only knows mapped places, not people'),
    'competitors': ('Understand who you compete with and how they perform.',
                    'Competitor prices, hours and observed busyness', 'A clear positioning for your business',
                    'Mapped competitors may be closed or missing from OpenStreetMap'),
    'capital': ('Know how much money you need before opening.', 'Written quotes',
                'A start-up budget with a contingency margin', 'Underestimating fit-out costs'),
    'costs': ('Know your monthly costs, which this report cannot estimate.', 'Rent quotes and salary estimates',
              'A monthly cost estimate to compare with revenue', 'Rent in busy sectors may absorb most of the margin'),
    'plan': ('Decide whether the numbers work.', 'Revenue scenarios plus your cost estimate',
             'A break-even estimate', 'Relying on a single optimistic scenario'),
    'legal': ('Operate legally from day one.', 'Written confirmation from the relevant offices',
              'A list of required registrations and timelines', 'Approval delays push back the opening date'),
    'suppliers': ('Secure reliable inputs and people.', 'Supplier terms and staff availability',
                  'Signed supplier terms and a staffing plan', 'Supplier or staff shortages'),
    'premises': ('Get the location ready to trade.', 'Lease agreement and fit-out schedule',
                 'Premises ready for opening', 'Fit-out overruns'),
    'launch': ('Start trading with low risk.', 'Daily sales and feedback', 'Proven day-to-day operations',
               'Slow initial uptake'),
    'monitor': ('Improve results with real data.', 'Sales records', 'Decisions based on actual sales',
                'Ignoring early warning signs'),
}


def default_roadmap(business):
    group = business_group(business)
    details = _GROUP_DETAILS[group]
    steps = []
    for key, title, weeks in _BASE_STEPS:
        objective, evidence, outcome, risks = _STEP_META[key]
        steps.append({
            'title': title,
            'objective': objective,
            'actions': details.get(key) or _COMMON_DETAILS.get(key) or [],
            'evidence': [evidence],
            'outcome': outcome,
            'risks': risks,
            'weeks': weeks,
        })
    return {'group': group, 'group_label': GROUP_LABELS[group], 'steps': steps}


def timeline(steps):
    """Sequential phases from the steps' week estimates (planning estimates)."""
    start = 0
    out = []
    for i, step in enumerate(steps):
        weeks = max(1, int(step.get('weeks') or 1))
        # The last step (monitoring) runs alongside trading, not before it.
        out.append({'title': step['title'], 'start': start, 'weeks': weeks})
        if i < len(steps) - 1:
            start += weeks
    return out


# ---------------------------------------------------------------------------
# Deterministic narrative
# ---------------------------------------------------------------------------

def _dominant_phrase(heat):
    return {'high': 'high', 'medium': 'medium', 'low': 'low'}.get(heat.get('dominant'), 'unknown')


def location_text(s):
    loc, pois, heat = s['location'], s['pois'], s['heatmap']
    fam = dict(pois.get('by_family') or [])
    commercial = fam.get('Shops', 0) + fam.get('Food & drink', 0)
    overview = (
        f"This report analyses {loc['name']} (latitude {loc['latitude']:.5f}, longitude {loc['longitude']:.5f}) "
        f"within a {loc['radius_m']:,} m radius. OpenStreetMap lists {pois.get('in_radius', 0):,} mapped features "
        f"inside that circle, of which {commercial:,} are shops or food-and-drink places."
    )
    if pois.get('status') != 'ok':
        overview = (f"This report analyses {loc['name']} within a {loc['radius_m']:,} m radius. "
                    "OpenStreetMap returned no mapped features with coordinates for this area, so most of the "
                    "analysis below could not be carried out.")
    top = ', '.join(f'{name.lower()} ({count:,})' for name, count in (pois.get('by_family') or [])[:4])
    character = (f"The most common kinds of mapped features are {top}. " if top else '') + (
        "These counts describe what has been mapped, not how many people visit. "
        f"The heatmap's dominant level is {_dominant_phrase(heat)}.")
    caveats = [
        'OpenStreetMap is volunteer-mapped; some businesses may be missing, closed or mis-tagged.',
        'Counts include buildings and road segments, not only businesses.',
        'The platform has no pedestrian footfall measurements; "visitors" figures are model estimates from mapped features.',
    ]
    return {'overview': overview, 'commercial_character': character, 'data_caveats': caveats}


def heatmap_text(s):
    heat = s['heatmap']
    c = heat['counts']
    if heat.get('placeholder_used'):
        return {
            'heatmap_explanation': 'No mapped features with coordinates were found, so no sector could be classified.',
            'spatial_pattern': 'The spatial pattern cannot be described for this location.',
        }
    explanation = (
        f"The 2 km circle is divided into 9 sectors: 3 distance rings × 3 compass wedges. Each sector is coloured by "
        f"how many mapped features it contains. {c['high']} sector(s) are High (15 or more features), "
        f"{c['medium']} Medium (5–14) and {c['low']} Low (1–4); {c['empty']} contain none. "
        f"Because at least one sector is {_dominant_phrase(heat)}, the platform treats the area as "
        f"{_dominant_phrase(heat)} intensity when recommending businesses."
    )
    busiest = sorted(heat['sectors'], key=lambda x: x['count'], reverse=True)
    top = busiest[0] if busiest and busiest[0]['count'] else None
    quiet = [x for x in heat['sectors'] if x['intensity'] in ('low', 'empty')]
    pattern = ''
    if top:
        pattern = (f"The densest sector is the {top['wedge'].split(' (')[0].lower()} wedge at {top['ring']} "
                   f"with {top['count']:,} mapped features. ")
    if quiet:
        pattern += f"{len(quiet)} sector(s) have few or no mapped features. "
    pattern += ('High density of mapped places suggests an established commercial or residential area, but it does '
                'not measure how many people are present at any time.')
    return {'heatmap_explanation': explanation, 'spatial_pattern': pattern}


def candidate_text(s, cand):
    """Why / strengths / weaknesses / validation for one candidate business."""
    rec = s.get('recommendation') or {}
    why = []
    if cand['source'].startswith('ML model (primary)'):
        why.append(f"The decision-tree model chose it for a {rec.get('intensity', 'unknown')}-intensity area"
                   + (f" with a '{rec['area_hint']}' character inferred from nearby places." if rec.get('area_hint') else '.'))
    elif cand['source'].startswith('ML model'):
        why.append(f"The model predicts it for a different intensity level ({cand['source'].split('for ')[-1].split(' ')[0]}), "
                   "so it is shown as an alternative, not as a match for this area's intensity.")
    else:
        why.append('You selected this business type.')
    strengths, weaknesses = [], []
    score = cand.get('potential_score')
    if score is not None:
        (strengths if score >= 60 else weaknesses).append(f'Revenue-engine potential score {score}/100.')
    comps = cand.get('competitors')
    if comps is not None:
        if comps == 0:
            weaknesses.append('No same-category competitors were matched in the map data; this can mean an '
                              'unserved niche or simply that similar places are tagged differently.')
        elif comps >= 10:
            weaknesses.append(f'{comps} similar places are mapped within 2 km (strong competition).')
        else:
            strengths.append(f'{comps} similar places are mapped within 2 km (proven but not saturated demand).')
    if cand.get('feasible') is True:
        strengths.append("The platform's feasibility rules mark it as feasible.")
    elif cand.get('feasible') is False:
        weaknesses.append("The platform's feasibility rules mark it as not feasible.")
    if cand.get('uses_default_assumptions'):
        weaknesses.append('The revenue engine has no specific parameters for this category and used generic defaults.')
    validation = ['Visit the area at peak and off-peak hours to observe actual customers.',
                  'Talk to at least 3 owners of similar businesses nearby.',
                  'Get real rent quotes before trusting any revenue figure.']
    return {'business': cand['business'], 'why': ' '.join(why), 'strengths': strengths or ['None identified from the available data.'],
            'weaknesses': weaknesses or ['None identified from the available data.'], 'validation_steps': validation}


def revenue_text(s):
    rev = s.get('revenue') or {}
    if rev.get('status') != 'ok':
        return {'revenue_explanation': 'Data unavailable for this analysis.', 'scenario_explanation': '',
                'assumption_notes': [rev.get('reason') or 'The revenue engine did not run.']}
    a = rev['assumptions']
    expl = (f"For the business type '{nice(rev['business_type'])}', the platform's Extended Huff engine estimates gross sales of about "
            f"{inr(rev['daily'])} per day, or {inr(rev['monthly'])} per month (30 days). This is revenue before any "
            "costs, not profit.")
    sc = rev.get('scenarios')
    scen = ''
    if sc:
        scen = (f"The engine also gives a range of {inr(sc['conservative'])} to {inr(sc['optimistic'])} per month "
                f"(±{sc['spread_pct']}%). The width comes from the engine's confidence score ({rev['confidence_score']}/100): "
                "lower confidence gives a wider range, between ±10% and ±40%. It is not a statistical confidence interval.")
    notes = [f"Average spend per customer assumed by the engine: {inr(a['avg_spend'])}.",
             f"Share of visitors who buy, assumed by the engine: {pct(a['conversion_rate'])}."]
    if rev.get('uses_default_assumptions'):
        notes.insert(0, f"The engine has no specific parameters for '{nice(rev['business_type'])}', so it used its "
                        "generic default values. Treat the forecast as very rough.")
    notes.append('Operating costs (rent, salaries, stock, utilities) are not in the data, so net profit cannot be calculated.')
    return {'revenue_explanation': expl, 'scenario_explanation': scen, 'assumption_notes': notes}


def summary_text(s, risks):
    loc, heat, rec, rev, feas = s['location'], s['heatmap'], s.get('recommendation') or {}, s.get('revenue') or {}, s.get('feasibility') or {}
    parts = [f"We analysed mapped places within {loc['radius_m']:,} m of {loc['name']}."]
    if not heat.get('placeholder_used'):
        parts.append(f"The area's dominant crowd-intensity level is {_dominant_phrase(heat)} "
                     f"({heat['counts']['high']} of 9 sectors are High).")
    if rec.get('status') == 'ok':
        parts.append(f"The platform's model suggests: {nice(rec['primary'])}.")
    if s.get('requested_business'):
        parts.append(f"You asked about: {nice(s['requested_business'])}. This report focuses on your choice.")
    if feas.get('status') == 'ok':
        parts.append(f"The feasibility rules mark it as {'feasible' if feas['feasible'] else 'not feasible'}.")
    if rev.get('status') == 'ok':
        parts.append(f"Estimated gross sales are about {inr(rev['monthly'])} per month; this is an estimate, not a guarantee.")
    advantages = []
    pos = rev.get('positive_factors') or []
    advantages.extend(pos[:3])
    if not advantages:
        advantages.append('No clear advantages could be identified from the available data.')
    key_risks = [r['risk'] for r in risks[:4]]
    next_steps = ['Visit the location at different times and count actual passers-by.',
                  'Visit the nearest competitors listed in this report.',
                  'Collect rent and cost quotes to estimate profit.',
                  'Confirm licences with the relevant authorities before signing a lease.']
    final = ('Treat this report as a starting point for your own checks, not as a decision. '
             'Do not invest on the basis of the model recommendation alone.')
    questions = ['How many people actually pass the premises you can rent, and when?',
                 'What will rent and monthly operating costs be?',
                 'Are the mapped competitors still open, and how busy are they?']
    return {'executive_summary': ' '.join(parts), 'key_advantages': advantages, 'key_risks': key_risks,
            'next_steps': next_steps, 'final_recommendation': final, 'open_questions': questions}


# ---------------------------------------------------------------------------
# Risk register
# ---------------------------------------------------------------------------

def risk_register(s):
    """
    Risks with 1–3 likelihood/impact ratings. 'measured' ratings follow fixed
    rules on platform outputs (stated in `rule`); 'qualitative' ratings are
    judgement for factors the platform has no data on.
    """
    risks = []
    comp = s.get('competition') or {}
    rev = s.get('revenue') or {}
    pois = s.get('pois') or {}

    if comp.get('status') == 'ok':
        near = comp['within_1000_m']
        lik = 3 if near >= 10 else 2 if near >= 3 else 1
        risks.append({'risk': 'Competition from similar businesses', 'likelihood': lik, 'impact': 2, 'basis': 'measured',
                      'evidence': f"{comp['count']} matched competitors within 2 km, {near} within 1 km.",
                      'rule': 'Likelihood 3 if 10+ within 1 km, 2 if 3–9, else 1.',
                      'mitigation': 'Differentiate on product, hours or service; visit competitors first.'})
    if rev.get('status') == 'ok':
        conf = rev['confidence_score']
        lik = 3 if conf < 50 else 2 if conf < 75 else 1
        risks.append({'risk': 'Revenue lower than forecast', 'likelihood': lik, 'impact': 3, 'basis': 'measured',
                      'evidence': f"Engine confidence {conf}/100; engine risk level {rev['risk_level']}.",
                      'rule': 'Likelihood 3 if confidence < 50, 2 if 50–74, else 1.',
                      'mitigation': 'Plan around the conservative scenario.'})
        if rev.get('uses_default_assumptions'):
            risks.append({'risk': 'Forecast uses generic assumptions', 'likelihood': 3, 'impact': 3, 'basis': 'measured',
                          'evidence': 'No category-specific spend or conversion parameters exist for this business.',
                          'rule': 'Always rated 3 × 3 when default parameters are used.',
                          'mitigation': 'Replace with your own estimates of customers and spend.'})
    if pois.get('status') == 'ok':
        density = pois['in_radius']
        lik = 3 if density < 50 else 2 if density < 300 else 1
        risks.append({'risk': 'Thin or incomplete map data', 'likelihood': lik, 'impact': 2, 'basis': 'measured',
                      'evidence': f'{density:,} mapped features within 2 km.',
                      'rule': 'Likelihood 3 if < 50 features, 2 if 50–299, else 1.',
                      'mitigation': 'Verify the area in person.'})
    risks.extend([
        {'risk': 'Uncertain customer demand', 'likelihood': 2, 'impact': 3, 'basis': 'qualitative',
         'evidence': 'The platform has no measured footfall or sales data.', 'rule': 'Judgement.',
         'mitigation': 'Run footfall counts and a small customer survey.'},
        {'risk': 'Rent and operating costs', 'likelihood': 2, 'impact': 3, 'basis': 'qualitative',
         'evidence': 'No rent or cost data is available to the platform.', 'rule': 'Judgement.',
         'mitigation': 'Collect quotes before committing.'},
        {'risk': 'Licensing or approval delays', 'likelihood': 2, 'impact': 2, 'basis': 'qualitative',
         'evidence': 'Requirements depend on the business and municipality.', 'rule': 'Judgement.',
         'mitigation': 'Start the approval process early.'},
        {'risk': 'Dependence on third-party data', 'likelihood': 1, 'impact': 2, 'basis': 'qualitative',
         'evidence': 'All map data comes from OpenStreetMap via the public Overpass API.', 'rule': 'Judgement.',
         'mitigation': 'Re-run the analysis before key decisions.'},
    ])
    risks.sort(key=lambda r: r['likelihood'] * r['impact'], reverse=True)
    return risks


CHECKLIST = [
    'I have visited the location at peak and off-peak times and counted customers myself.',
    'I have visited the nearest competitors and compared prices and quality.',
    'I have written rent quotes for at least two premises.',
    'I have estimated monthly operating costs and a break-even sales level.',
    'My plan still works under the conservative revenue scenario.',
    'I have confirmed the licences and registrations my business needs.',
    'I have a start-up budget with a contingency margin.',
    'I have discussed the plan with an accountant or experienced operator.',
]
