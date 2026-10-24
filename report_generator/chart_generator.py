"""
Matplotlib charts for the PDF, drawn only from snapshot values.

Each function returns a PNG data URI, or None when the data it needs is
missing (the template then prints "Data unavailable for this analysis.").
"""
import base64
import io
import math

import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402
import matplotlib.ticker  # noqa: E402,F401
from matplotlib import font_manager  # noqa: E402
from matplotlib.patches import Circle, Rectangle  # noqa: E402

from . import theme  # noqa: E402
from .content import inr, nice  # noqa: E402
from .pdf_generator import REPORT_FONT_DIR  # noqa: E402

# Heat colours keep the website legend's meaning (see theme.py).
INTENSITY_COLORS = theme.INTENSITY
INK = theme.TEXT            # labels and values
MUTED = theme.MUTED          # thresholds, secondary notes
ACCENT = theme.ACCENT       # primary data series

for _font in REPORT_FONT_DIR.glob('*.ttf'):
    font_manager.fontManager.addfont(str(_font))
# The family name matplotlib registers comes from the font file ("DM Sans 9pt" for DM Sans).
_BODY_FAMILY = font_manager.FontProperties(fname=str(REPORT_FONT_DIR / 'DMSans-Regular.ttf')).get_name()

plt.rcParams.update({
    # DM Sans for chart text; DejaVu Sans (bundled with matplotlib) covers any missing symbol.
    'font.family': [_BODY_FAMILY, 'DejaVu Sans'],
    'font.size': 9,
    'figure.facecolor': theme.BG,
    'axes.facecolor': theme.BG,
    'savefig.facecolor': theme.BG,
    'text.color': theme.TEXT,
    'axes.edgecolor': theme.LINE,
    'axes.labelcolor': theme.MUTED,
    'xtick.color': theme.MUTED,
    'ytick.color': theme.MUTED,
    'xtick.labelcolor': theme.TEXT,
    'ytick.labelcolor': theme.TEXT,
    'legend.facecolor': theme.BG,
    'legend.edgecolor': theme.LINE,
    'legend.labelcolor': theme.TEXT,
    'axes.spines.top': False,
    'axes.spines.right': False,
})


def _to_data_uri(fig):
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=170, bbox_inches='tight', facecolor=theme.BG)
    plt.close(fig)
    return 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode('ascii')


def sector_chart(heat):
    if not heat or heat.get('placeholder_used') or not heat.get('sectors'):
        return None
    sectors = heat['sectors']
    labels = [f"{s['wedge'].split(' (')[0]}\n{s['ring']}" for s in sectors]
    counts = [s['count'] for s in sectors]
    colors = [INTENSITY_COLORS[s['intensity']] for s in sectors]
    fig, ax = plt.subplots(figsize=(7.2, 3.2))
    bars = ax.bar(range(len(sectors)), counts, color=colors, edgecolor=theme.BG)
    for bar, value in zip(bars, counts):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(), f'{value:,}',
                ha='center', va='bottom', fontsize=7.5, color=INK)
    if max(counts or [0]) <= 60:
        for y, lvl in ((15, 'High threshold (15)'), (5, 'Medium threshold (5)')):
            ax.axhline(y, color=MUTED, linestyle='--', linewidth=0.8)
            ax.text(len(sectors) - 0.5, y, lvl, ha='right', va='bottom', fontsize=7, color=MUTED)
    ax.set_xticks(range(len(sectors)), labels, fontsize=6.5)
    ax.set_ylabel('Mapped features in sector')
    handles = [Rectangle((0, 0), 1, 1, color=INTENSITY_COLORS[k]) for k in ('high', 'medium', 'low', 'empty')]
    ax.legend(handles, ['High (15+)', 'Medium (5–14)', 'Low (1–4)', 'No features'], fontsize=7,
              frameon=False, ncol=4, loc='upper center', bbox_to_anchor=(0.5, 1.15))
    return _to_data_uri(fig)


def poi_family_chart(pois):
    families = (pois or {}).get('by_family') or []
    if not families:
        return None
    families = list(reversed(families[:10]))
    fig, ax = plt.subplots(figsize=(7.2, 3.0))
    names = [f[0] for f in families]
    values = [f[1] for f in families]
    ax.barh(names, values, color=ACCENT)
    for i, v in enumerate(values):
        ax.text(v, i, f' {v:,}', va='center', fontsize=7.5, color=INK)
    ax.set_xlabel('Number of mapped OpenStreetMap features within 2 km')
    ax.margins(x=0.15)
    return _to_data_uri(fig)


def competitor_distance_chart(comp):
    if not comp or comp.get('status') != 'ok' or not comp.get('count'):
        return None
    bins = comp['distance_bins']
    fig, ax = plt.subplots(figsize=(6.4, 2.6))
    labels = [b[0] for b in bins]
    values = [b[1] for b in bins]
    ax.bar(labels, values, color=theme.SERIES['sky'])
    for i, v in enumerate(values):
        ax.text(i, v, f'{v}', ha='center', va='bottom', fontsize=8, color=INK)
    ax.set_ylabel('Matched competitors')
    ax.set_xlabel('Distance from the selected location')
    return _to_data_uri(fig)


def candidate_chart(candidates):
    rows = [c for c in candidates or [] if c.get('potential_score') is not None]
    if not rows:
        return None
    rows = list(reversed(rows))
    names = [nice(c['business']) + (' *' if c.get('uses_default_assumptions') else '') for c in rows]
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(7.4, 0.55 * len(rows) + 1.3), sharey=True)
    scores = [c['potential_score'] for c in rows]
    ax1.barh(names, scores, color=ACCENT)
    ax1.set_xlim(0, 100)
    ax1.set_xlabel('Potential score (0–100 index)')
    for i, v in enumerate(scores):
        ax1.text(v, i, f' {v}', va='center', fontsize=8, color=INK)
    revenue = [c['monthly_revenue'] for c in rows]
    ax2.barh(names, revenue, color=theme.SERIES['navy'])
    ax2.set_xlabel('Estimated gross sales per month (₹)')
    ax2.margins(x=0.35)
    for i, v in enumerate(revenue):
        ax2.text(v, i, ' ' + inr(v), va='center', fontsize=8, color=INK)
    ax2.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda x, _: inr(x)))
    plt.setp(ax2.get_xticklabels(), rotation=25, ha='right', fontsize=7)
    return _to_data_uri(fig)


def scenario_chart(revenue):
    sc = (revenue or {}).get('scenarios')
    if not sc:
        return None
    labels = ['Conservative', 'Base', 'Optimistic']
    values = [sc['conservative'], sc['base'], sc['optimistic']]
    fig, ax = plt.subplots(figsize=(5.8, 2.7))
    ax.bar(labels, values, color=[theme.SERIES['slate'], ACCENT, theme.SERIES['navy']], width=0.55)
    for i, v in enumerate(values):
        ax.text(i, v, inr(v), ha='center', va='bottom', fontsize=8.5, color=INK)
    ax.set_ylabel('Gross sales per month (₹)')
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda x, _: inr(x)))
    ax.margins(y=0.18)
    return _to_data_uri(fig)


def timeline_chart(phases):
    if not phases:
        return None
    fig, ax = plt.subplots(figsize=(7.2, 0.32 * len(phases) + 1.0))
    for i, ph in enumerate(phases):
        ax.barh(i, ph['weeks'], left=ph['start'], color=ACCENT if i < len(phases) - 1 else theme.SERIES['navy'], height=0.6)
        ax.text(ph['start'] + ph['weeks'] + 0.2, i, f"{ph['weeks']} wk", va='center', fontsize=7, color=MUTED)
    ax.set_yticks(range(len(phases)), [f"{i + 1}. {p['title']}" for i, p in enumerate(phases)], fontsize=7.5)
    ax.invert_yaxis()
    ax.set_xlabel('Weeks from start (planning estimate)')
    ax.margins(x=0.08)
    return _to_data_uri(fig)


def risk_matrix_chart(risks):
    if not risks:
        return None
    fig, ax = plt.subplots(figsize=(5.0, 3.6))
    for li in range(1, 4):
        for im in range(1, 4):
            color = theme.RISK_CELLS[li * im]
            ax.add_patch(Rectangle((im - 0.5, li - 0.5), 1, 1, facecolor=color, edgecolor=theme.BG, linewidth=2))
    cells = {}
    for idx, r in enumerate(risks, start=1):
        cells.setdefault((r['impact'], r['likelihood']), []).append((idx, r['basis']))
    for (im, li), items in cells.items():
        for j, (idx, basis) in enumerate(items):
            dx = (j % 3 - 1) * 0.25
            dy = -(j // 3) * 0.25 + (0.1 if len(items) > 3 else 0)
            marker = 'o' if basis == 'measured' else 's'
            ax.scatter(im + dx, li + dy, s=230, marker=marker, color=theme.BG, edgecolor=theme.ACCENT, zorder=3)
            ax.text(im + dx, li + dy, str(idx), ha='center', va='center', fontsize=7.5, color=INK, zorder=4)
    ax.set_xlim(0.5, 3.5)
    ax.set_ylim(0.5, 3.5)
    ax.set_xticks([1, 2, 3], ['Low', 'Medium', 'High'])
    ax.set_yticks([1, 2, 3], ['Low', 'Medium', 'High'])
    ax.set_xlabel('Impact')
    ax.set_ylabel('Likelihood')
    ax.scatter([], [], marker='o', color=theme.BG, edgecolor=theme.ACCENT, label='Rated from platform data')
    ax.scatter([], [], marker='s', color=theme.BG, edgecolor=theme.ACCENT, label='Qualitative judgement')
    ax.legend(fontsize=7, frameon=False, loc='upper center', bbox_to_anchor=(0.5, 1.16), ncol=2)
    return _to_data_uri(fig)


def _projector(lat0):
    k = math.cos(math.radians(lat0))

    def project(lat, lon):
        # Local equirectangular projection in metres; fine at a 2 km scale.
        return (lon * k * 111320.0, lat * 110540.0)
    return project


def _map_frame(ax, lat, lon, radius_m, project):
    cx, cy = project(lat, lon)
    ax.add_patch(Circle((cx, cy), radius_m, fill=False, edgecolor=theme.ACCENT, linewidth=1.0, linestyle='--'))
    ax.set_xlim(cx - radius_m * 1.08, cx + radius_m * 1.08)
    ax.set_ylim(cy - radius_m * 1.08, cy + radius_m * 1.08)
    ax.set_aspect('equal')
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_visible(True)
        spine.set_color(theme.LINE)
    ax.plot(cx, cy, marker='*', markersize=14, color=theme.ACCENT, markeredgecolor=theme.BG, zorder=5)
    # 500 m scale bar
    x0, y0 = cx - radius_m * 1.0, cy - radius_m * 1.0
    ax.plot([x0, x0 + 500], [y0, y0], color=INK, linewidth=2)
    ax.text(x0 + 250, y0 + 40, '500 m', ha='center', fontsize=7, color=INK)
    ax.annotate('N', xy=(cx + radius_m * 0.98, cy + radius_m * 0.98), xytext=(cx + radius_m * 0.98, cy + radius_m * 0.78),
                arrowprops={'arrowstyle': '->', 'color': INK}, ha='center', fontsize=8, color=INK)
    return cx, cy


def location_map_chart(snapshot, max_points=8000):
    """Mapped features around the location, plotted from their OSM coordinates."""
    pois = snapshot.get('pois') or {}
    points = pois.get('points') or []
    if not points:
        return None
    loc = snapshot['location']
    project = _projector(loc['latitude'])
    step = max(1, len(points) // max_points)
    fig, ax = plt.subplots(figsize=(5.6, 5.6))
    palette = theme.POI_FAMILIES
    groups = {}
    for la, lo, fam in points[::step]:
        groups.setdefault(fam if fam in palette else 'Other mapped features', []).append(project(la, lo))
    other = groups.pop('Other mapped features', [])
    if other:
        xs, ys = zip(*other)
        ax.scatter(xs, ys, s=1.2, color=theme.POI_OTHER, label='Buildings, roads & other', zorder=1)
    for fam, pts in groups.items():
        xs, ys = zip(*pts)
        ax.scatter(xs, ys, s=4, color=palette[fam], label=fam, zorder=2)
    _map_frame(ax, loc['latitude'], loc['longitude'], loc['radius_m'], project)
    ax.legend(fontsize=6.5, loc='upper left', frameon=True, markerscale=2.5)
    return _to_data_uri(fig)


def sector_map_chart(snapshot):
    """
    Fallback heatmap: the platform's sector circles drawn at their real
    centroids with the website's radii and colours. Used only when the live
    screenshot is unavailable, and captioned as a reconstruction.
    """
    heat = snapshot.get('heatmap') or {}
    if not heat or heat.get('placeholder_used'):
        return None
    loc = snapshot['location']
    project = _projector(loc['latitude'])
    fig, ax = plt.subplots(figsize=(5.6, 5.6))
    cx, cy = project(loc['latitude'], loc['longitude'])
    # Ring and wedge boundaries of the sector grid.
    for r in (loc['radius_m'] / 3, 2 * loc['radius_m'] / 3):
        ax.add_patch(Circle((cx, cy), r, fill=False, edgecolor=theme.LINE, linewidth=0.8))
    for angle in (-60, 60, 180):
        a = math.radians(angle)
        ax.plot([cx, cx + loc['radius_m'] * math.cos(a)], [cy, cy + loc['radius_m'] * math.sin(a)],
                color=theme.LINE, linewidth=0.8)
    radii = {'high': 800, 'medium': 600, 'low': 400}  # same as static/js/main.js
    for level in ('low', 'medium', 'high'):
        for area in (heat.get('areas') or {}).get(level, []):
            x, y = project(area['latitude'], area['longitude'])
            ax.add_patch(Circle((x, y), radii[level], color=INTENSITY_COLORS[level], alpha=0.30, linewidth=0))
            ax.plot(x, y, 'o', color=INTENSITY_COLORS[level], markeredgecolor=theme.BG, markersize=7)
            ax.text(x, y + 90, f"{area['count']:,}", ha='center', fontsize=7, color=INK)
    _map_frame(ax, loc['latitude'], loc['longitude'], loc['radius_m'], project)
    handles = [Rectangle((0, 0), 1, 1, color=INTENSITY_COLORS[k], alpha=0.6) for k in ('high', 'medium', 'low')]
    ax.legend(handles, ['High', 'Medium', 'Low'], fontsize=7, loc='upper left')
    return _to_data_uri(fig)


def build_all(snapshot, risks, phases):
    return {
        'location_map': location_map_chart(snapshot),
        'sectors': sector_chart(snapshot.get('heatmap')),
        'sector_map': sector_map_chart(snapshot),
        'poi_families': poi_family_chart(snapshot.get('pois')),
        'competitor_distance': competitor_distance_chart(snapshot.get('competition')),
        'candidates': candidate_chart(snapshot.get('candidates')),
        'scenarios': scenario_chart(snapshot.get('revenue')),
        'timeline': timeline_chart(phases),
        'risk_matrix': risk_matrix_chart(risks),
    }
