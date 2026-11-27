from decimal import Decimal, ROUND_CEILING

FLOW_FEE_PERCENT = Decimal("0.0289")
FLOW_VAT_PERCENT = Decimal("0.19")
FLOW_EFFECTIVE_FEE_RATE = FLOW_FEE_PERCENT * (Decimal("1") + FLOW_VAT_PERCENT)


def flow_checkout_amount(debt_amount):
    """Return the gross checkout amount needed to cover Flow's estimated fee."""
    debt_amount = int(debt_amount)
    if debt_amount <= 0:
        return 0, 0
    gross = int(
        (Decimal(debt_amount) / (Decimal("1") - FLOW_EFFECTIVE_FEE_RATE)).quantize(
            Decimal("1"), rounding=ROUND_CEILING
        )
    )
    return gross, gross - debt_amount
