from decimal import ROUND_HALF_UP, Decimal


def format_gbp(pence: int | str | Decimal) -> str:
    """Exact pounds; trailing .00 trimmed. Accepts pence as an int or a Decimal string."""
    return f"£{Decimal(pence) / 100:,.2f}".removesuffix(".00")


def format_gbp_round(pence: int | str | Decimal) -> str:
    """Whole pounds, half-up — for running amounts carrying intermediate fractional pence."""
    pounds = (Decimal(pence) / 100).quantize(Decimal(1), rounding=ROUND_HALF_UP)
    return f"£{pounds:,}"
