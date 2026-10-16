"""
Editorial palette shared by the PDF stylesheet (templates/reports/report.html),
the matplotlib charts and the SVG flowcharts: warm ivory pages, royal blue
accents, deep navy and charcoal.

Charts and flowcharts are drawn on IVORY so they sit flush on cream pages and
read as cards on the navy / royal-blue pages. Heat colours keep the website
legend's meaning (red = high, orange = medium, green = low).
"""
IVORY = '#F4EFE6'          # page background
PAPER = '#FBF8F2'          # cards and panels on ivory pages
NAVY = '#0E1A3B'           # dark section pages, strong text
ROYAL = '#2443D6'          # accent: rules, connectors, primary data series
ROYAL_SOFT = '#E3E8FB'     # tinted fills
CHARCOAL = '#1F1F23'       # body text

BG = IVORY
PANEL = PAPER
LINE = '#D8CFBE'           # hairlines, gridlines
ACCENT = ROYAL
TEXT = CHARCOAL
MUTED = '#6E6758'          # captions, secondary text, ticks

SERIES = {
    'primary': ROYAL,
    'navy': NAVY,
    'sky': '#8EA2EE',
    'slate': '#9A9384',
}

INTENSITY = {'high': '#D64545', 'medium': '#E8962E', 'low': '#3E9B5F', 'empty': '#D8CFBE'}

POI_FAMILIES = {
    'Shops': ROYAL,
    'Food & drink': '#D64545',
    'Healthcare': '#3E9B5F',
    'Education': '#8B5CF6',
    'Transport & parking': '#E8962E',
    'Offices': '#0E8A9A',
}
POI_OTHER = '#CDC5B4'

# Flowchart node styles: (fill, stroke). Connectors use ROYAL.
FLOW = {
    'start': (ROYAL_SOFT, ROYAL),
    'process': (PAPER, '#B7AE9C'),
    'model': ('#E9ECF4', NAVY),
    'output': ('#E5F1E8', '#3E9B5F'),
    'decision': ('#FBF0DF', '#E8962E'),
    'warn': ('#FBE7E5', '#D64545'),
}

# Risk matrix cell tints by likelihood x impact.
RISK_CELLS = {1: '#E5F1E8', 2: '#E5F1E8', 3: '#F7F0D8', 4: '#FBEBD3', 6: '#F9DCC7', 9: '#F6D2CE'}

DISPLAY_FONT = 'Fraunces'
BODY_FONT = 'DM Sans'
MONO_FONT = 'DM Mono'
