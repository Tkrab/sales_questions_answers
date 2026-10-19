from django import template

register = template.Library()


@register.filter
def score_level(value):
    try:
        score = float(value)
    except (TypeError, ValueError):
        return "na"
    if score >= 80:
        return "good"
    if score >= 50:
        return "mid"
    return "low"
