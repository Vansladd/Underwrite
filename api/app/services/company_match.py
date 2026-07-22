from __future__ import annotations

import re

from rapidfuzz.fuzz import token_sort_ratio

# LTD vs LIMITED etc. score two identical companies below 0.85 without expansion. See R5.2.
_EXPANSIONS = {
    "LTD": "LIMITED",
    "PLC": "PUBLIC LIMITED COMPANY",
    "LLP": "LIMITED LIABILITY PARTNERSHIP",
}


def normalise_company_name(name: str) -> str:
    text = name.upper().replace("&", " AND ")
    text = re.sub(r"[^\w\s]", " ", text)
    tokens = text.split()
    if tokens and tokens[0] == "THE":
        tokens = tokens[1:]
    return " ".join(_EXPANSIONS.get(token, token) for token in tokens)


def name_match_score(extracted: str, official: str) -> float:
    score = token_sort_ratio(normalise_company_name(extracted), normalise_company_name(official))
    return score / 100
