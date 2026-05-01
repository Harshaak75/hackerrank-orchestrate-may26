from __future__ import annotations


COMPANY_KEYWORDS = {
    "HackerRank": {
        "hackerrank",
        "assessment",
        "candidate",
        "coding test",
        "interview",
        "recruiter",
        "screen",
        "skillup",
        "test invite",
    },
    "Claude": {
        "anthropic",
        "claude",
        "workspace",
        "seat",
        "team plan",
        "enterprise",
        "pro plan",
        "console",
        "organization",
    },
    "Visa": {
        "visa",
        "card",
        "payment",
        "merchant",
        "atm",
        "travel",
        "exchange rate",
        "fraud",
        "bank",
    },
}


def detect_company(issue: str, subject: str = "", company_value: str = "") -> str:
    normalized_company = (company_value or "").strip()
    if normalized_company in {"HackerRank", "Claude", "Visa"}:
        return normalized_company

    haystack = f"{subject} {issue}".lower()
    best_company = "Unknown"
    best_score = 0

    for company, keywords in COMPANY_KEYWORDS.items():
        score = sum(1 for keyword in keywords if keyword in haystack)
        if score > best_score:
            best_company = company
            best_score = score

    return best_company
