from django import template

register = template.Library()


@register.filter
def clp(value):
    """Format CLP integers with a dot as the thousands separator."""
    try:
        return f"{int(value):,}".replace(",", ".")
    except (TypeError, ValueError):
        return value
