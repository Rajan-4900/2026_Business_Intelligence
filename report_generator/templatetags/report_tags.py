from django import template

from report_generator import content

register = template.Library()


@register.filter
def inr(value):
    return content.inr(value)


@register.filter
def nice(value):
    return content.nice(value)


@register.filter
def pct(value, digits=0):
    if value is None:
        return '—'
    return content.pct(value, int(digits))


@register.filter
def level_word(value):
    return {1: 'Low', 2: 'Medium', 3: 'High'}.get(value, '—')


@register.filter
def get(mapping, key):
    try:
        return mapping.get(key)
    except AttributeError:
        return None
