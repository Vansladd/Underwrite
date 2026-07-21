from app.domain.rating import FactorApplication, RatingResult, Reason


def factor_to_json(factor: FactorApplication) -> dict:
    return {
        "code": factor.code,
        "band_label": factor.band_label,
        # str, never float: a Decimal through JSON loses the exactness D6 exists to keep.
        "multiplier": str(factor.multiplier),
        "reason": factor.reason,
        "premium_before_pence": str(factor.premium_before_pence),
        "premium_after_pence": str(factor.premium_after_pence),
    }


def reason_to_json(reason: Reason) -> dict:
    return {"code": reason.code.value, "message": reason.message}


def rating_to_orm_kwargs(result: RatingResult) -> dict:
    return {
        "rating_version": result.rating_version,
        "decision": result.decision,
        "base_premium_pence": result.base_premium_pence,
        "indicative_premium_pence": result.indicative_premium_pence,
        "annual_premium_pence": result.annual_premium_pence,
        "factors": [factor_to_json(factor) for factor in result.factors],
        "refer_reasons": [reason_to_json(reason) for reason in result.refer_reasons],
        "decline_reasons": [reason_to_json(reason) for reason in result.decline_reasons],
    }
