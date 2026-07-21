from enum import IntEnum, StrEnum


class Sector(StrEnum):
    SAAS = "saas"
    FINTECH = "fintech"
    HEALTHTECH = "healthtech"
    ECOMMERCE = "ecommerce"
    AI_ML = "ai_ml"
    MARKETPLACE = "marketplace"
    CRYPTO = "crypto"
    OTHER = "other"


class DataVolume(StrEnum):
    UNDER_10K = "under_10k"
    TEN_K_TO_100K = "10k_100k"
    HUNDRED_K_TO_1M = "100k_1m"
    OVER_1M = "over_1m"


class RequestedLimit(IntEnum):
    GBP_250K = 250_000
    GBP_500K = 500_000
    GBP_1M = 1_000_000
    GBP_2M = 2_000_000


class CompanyStatus(StrEnum):
    ACTIVE = "active"
    DISSOLVED = "dissolved"
    LIQUIDATION = "liquidation"
    RECEIVERSHIP = "receivership"
    ADMINISTRATION = "administration"
    VOLUNTARY_ARRANGEMENT = "voluntary-arrangement"
    CONVERTED_CLOSED = "converted-closed"
    INSOLVENCY_PROCEEDINGS = "insolvency-proceedings"
    REGISTERED = "registered"
    REMOVED = "removed"
    CLOSED = "closed"
    OPEN = "open"


TERMINAL_COMPANY_STATUSES = frozenset(
    {
        CompanyStatus.DISSOLVED,
        CompanyStatus.LIQUIDATION,
        CompanyStatus.RECEIVERSHIP,
        CompanyStatus.ADMINISTRATION,
        CompanyStatus.CONVERTED_CLOSED,
        CompanyStatus.REMOVED,
        CompanyStatus.CLOSED,
    }
)


class Decision(IntEnum):
    AUTO_APPROVE = 0
    REFER = 1
    DECLINE = 2

    @classmethod
    def worst(cls, decisions: "list[Decision] | tuple[Decision, ...]") -> "Decision":
        return max(decisions, default=cls.AUTO_APPROVE)


class ReasonCode(StrEnum):
    LOW_EXTRACTION_CONFIDENCE = "LOW_EXTRACTION_CONFIDENCE"
    MISSING_FIELDS = "MISSING_FIELDS"
    CH_NOT_FOUND = "CH_NOT_FOUND"
    CH_NAME_MISMATCH = "CH_NAME_MISMATCH"
    CH_STATUS_NOT_ACTIVE = "CH_STATUS_NOT_ACTIVE"
    CH_DISCREPANCY = "CH_DISCREPANCY"
    REVENUE_ABOVE_AUTHORITY = "REVENUE_ABOVE_AUTHORITY"
    SECTOR_UNCLASSIFIED = "SECTOR_UNCLASSIFIED"
    PRIOR_CLAIM = "PRIOR_CLAIM"

    SECTOR_OUT_OF_APPETITE = "SECTOR_OUT_OF_APPETITE"
    CLAIMS_HISTORY = "CLAIMS_HISTORY"
    TOO_NEW = "TOO_NEW"
    CH_STATUS_TERMINAL = "CH_STATUS_TERMINAL"
