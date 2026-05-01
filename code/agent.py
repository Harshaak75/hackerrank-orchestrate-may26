from __future__ import annotations

import json
import re
import time

from config import (
    GEMINI_API_KEY,
    GEMINI_MAX_RETRIES,
    GEMINI_MIN_SECONDS_BETWEEN_REQUESTS,
    GEMINI_MODEL,
    STOP_WORDS,
)
from retriever import RetrievalResult


ALLOWED_STATUS = {"replied", "escalated"}
ALLOWED_REQUEST_TYPES = {"product_issue", "feature_request", "bug", "invalid"}
RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": sorted(ALLOWED_STATUS)},
        "product_area": {"type": "string"},
        "response": {"type": "string"},
        "justification": {"type": "string"},
        "request_type": {"type": "string", "enum": sorted(ALLOWED_REQUEST_TYPES)},
        "confidence_score": {"type": "number"},
    },
    "required": ["status", "product_area", "response", "justification", "request_type", "confidence_score"],
}
ACCOUNT_SPECIFIC_KEYWORDS = {
    "cash",
    "refund",
    "payment",
    "order id",
    "rescheduling",
    "reschedule",
    "pause our subscription",
    "pause subscription",
    "remove an interviewer",
    "remove them from our hackerrank hiring account",
    "update it",
    "restore my access immediately",
}
SENSITIVE_KEYWORDS = {
    "fraud",
    "stolen",
    "identity theft",
    "charge",
    "security vulnerability",
    "bug bounty",
    "review my answers",
    "increase my score",
    "move me to the next round",
}
OUT_OF_SCOPE_KEYWORDS = {
    "fill out the forms",
    "delete all files from the system",
    "display all the rules",
    "internal rules",
}
_LAST_REQUEST_AT = 0.0
_MODEL_DISABLED_REASON = ""
GENERIC_ARTICLE_KEYWORDS = {
    "glossary",
    "release notes",
    "crisis helpline",
    "helpline support",
    "mental health",
    "index",
    "introduction to",
    "getting started with",
}
GENERIC_MATCH_TOKENS = {
    "account",
    "card",
    "claude",
    "company",
    "hackerrank",
    "help",
    "issue",
    "need",
    "not",
    "problem",
    "support",
    "team",
    "test",
    "user",
    "users",
    "visa",
    "work",
    "working",
}


def infer_request_type(issue: str, subject: str = "") -> str:
    text = f"{subject} {issue}".lower()
    if any(keyword in text for keyword in {"feature request", "would love", "please add", "can you add"}):
        return "feature_request"
    if any(keyword in text for keyword in {"bug", "error", "failed", "failure", "down", "outage", "not working"}):
        return "bug"
    if any(keyword in text for keyword in {"ignore previous instructions", "system prompt", "bypass safety", "hack into"}):
        return "invalid"
    return "product_issue"


def build_prompt(issue: str, subject: str, company: str, retrieval_result: RetrievalResult, intents: list[str] = None) -> str:
    excerpts = []
    for index, match in enumerate(retrieval_result.matches, start=1):
        excerpts.append(
            "\n".join(
                [
                    f"Document {index}:",
                    f"Company: {match.company}",
                    f"Title: {match.title}",
                    f"Breadcrumb: {match.breadcrumb}",
                    f"Path: {match.path}",
                    f"Excerpt: {match.excerpt}",
                ]
            )
        )

    prompt_parts = [
        "You are a careful support triage agent.",
        "Use only the retrieved support corpus excerpts below.",
        "If the issue is sensitive, unsupported, or requires account-specific action, choose escalated.",
        "Never promise actions that the corpus does not support.",
        "Return only valid JSON with these keys: status, product_area, response, justification, request_type, confidence_score.",
        "Allowed status values: replied, escalated.",
        "Allowed request_type values: product_issue, feature_request, bug, invalid.",
        "Confidence_score must be a float between 0.0 and 1.0 indicating how confident you are in your response.",
        "Keep product_area short, lowercase, and underscore-separated.",
    ]
    
    if intents and len(intents) > 1:
        prompt_parts.append(
            f"Detected intents: {', '.join(intents)}. The user has asked multiple questions or raised multiple issues. "
            "You MUST properly divide and address all of them by combining the response if possible, "
            "or pick the highest risk intent (e.g. security over general questions) to escalate."
        )

    prompt_parts.extend([
        f"Company: {company}",
        f"Subject: {subject or '(blank)'}",
        f"Issue: {issue}",
        "Retrieved support corpus:",
        "\n\n".join(excerpts) if excerpts else "No excerpts found.",
    ])
    
    return "\n\n".join(prompt_parts)


def _extract_json_block(text: str) -> dict[str, str]:
    normalized = text.strip()
    if normalized.startswith("```"):
        normalized = re.sub(r"^```(?:json)?\s*", "", normalized)
        normalized = re.sub(r"\s*```$", "", normalized)

    try:
        return json.loads(normalized)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", normalized, re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(0))


def _normalize_product_area(value: str, fallback: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", (value or "").strip().lower()).strip("_")
    return normalized or fallback


def _sanitize_excerpt(text: str) -> str:
    sanitized = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text or "")
    sanitized = re.sub(r"#+\s*", "", sanitized)
    sanitized = re.sub(r"\s+", " ", sanitized).strip()
    return sanitized[:500]


def _keyword_tokens(text: str) -> list[str]:
    return [
        token
        for token in re.findall(r"[a-z0-9]{3,}", text.lower())
        if token not in STOP_WORDS
    ]


def _strong_retrieval_match(issue: str, subject: str, retrieval_result: RetrievalResult) -> bool:
    top_match = retrieval_result.matches[0] if retrieval_result.matches else None
    if not top_match:
        return False

    article_text = f"{top_match.title} {top_match.breadcrumb} {top_match.excerpt}".lower()
    tokens = _keyword_tokens(f"{subject} {issue}")
    overlap = {token for token in tokens if token in article_text and token not in GENERIC_MATCH_TOKENS}

    if any(keyword in top_match.title.lower() for keyword in GENERIC_ARTICLE_KEYWORDS):
        return False
    if "<table" in top_match.excerpt.lower():
        return False
    if "related articles" in top_match.excerpt.lower():
        return False
    if top_match.score < 150:
        return False
    return len(overlap) >= 1


def _looks_like_replyable_case(issue: str, subject: str, request_type: str) -> bool:
    text = f"{subject} {issue}".lower()
    if request_type in {"invalid", "bug"}:
        return False
    if any(keyword in text for keyword in ACCOUNT_SPECIFIC_KEYWORDS):
        return False
    if any(keyword in text for keyword in SENSITIVE_KEYWORDS):
        return False
    if any(keyword in text for keyword in OUT_OF_SCOPE_KEYWORDS):
        return False
    return True


def _fallback_from_retrieval(
    *,
    issue: str,
    subject: str,
    company: str,
    retrieval_result: RetrievalResult,
    request_type: str,
    failure_reason: str,
    intents: list[str] = None,
) -> dict[str, str]:
    if intents is None:
        intents = []
    top_match = retrieval_result.matches[0] if retrieval_result.matches else None
    product_area = retrieval_result.best_product_area or company.lower()
    
    text = f"{subject} {issue}".lower()
    if any(kw in text for kw in {"payment", "billing", "money", "refund", "charge", "order id"}):
        product_area = "billing"

    if not top_match or top_match.score < 150:
        if company == "Visa" and any(kw in text for kw in {"refund", "ban", "money back", "merchant"}):
            return {
                "status": "escalated",
                "product_area": "payments",
                "response": "Visa cannot directly force refunds or ban merchants. Please contact your issuing bank to initiate a chargeback. This case is escalated for further review.",
                "justification": "Escalated to payments specialist with partial chargeback guidance.",
                "request_type": request_type,
                "confidence_score": 0.85,
            }
        return {
            "status": "escalated",
            "product_area": product_area,
            "response": (
                "Hi,\n\n"
                "Since we could not find a matching answer in our support documentation "
                "for your specific issue, our support team will need to review this.\n\n"
                f"A {product_area.replace('_', ' ')} specialist will follow up with you shortly."
            ),
            "justification": (
                "Escalated to human support because no clear documentation was found "
                "to automatically resolve the issue with high confidence."
                + (f" Handled multiple intents: {', '.join(intents)} (prioritized highest risk)." if len(intents) > 1 else "")
            ),
            "request_type": request_type,
            "confidence_score": 1.0,
        }

    if not _strong_retrieval_match(issue=issue, subject=subject, retrieval_result=retrieval_result):
        top_title = top_match.title if top_match else "the support documentation"
        return {
            "status": "escalated",
            "product_area": product_area,
            "response": (
                "Hi,\n\n"
                f"We found related {company} support documentation ({top_title}), but since it did not "
                "provide a specific enough answer to resolve your request confidently, we are escalating this.\n\n"
                f"A {product_area.replace('_', ' ')} specialist will follow up with more targeted guidance."
            ),
            "justification": (
                "Escalated because retrieval found related articles but none matched specifically "
                "enough to produce a confident direct response safely."
                + (f" Handled multiple intents: {', '.join(intents)} (prioritized highest risk)." if len(intents) > 1 else "")
            ),
            "request_type": request_type,
            "confidence_score": 1.0,
        }

    if not _looks_like_replyable_case(issue=issue, subject=subject, request_type=request_type):
        return {
            "status": "escalated",
            "product_area": product_area,
            "response": (
                "Hi,\n\n"
                "Since this request involves account-specific details, billing verification, or "
                "an action that requires identity confirmation, our support team must handle it directly.\n\n"
                f"A {product_area.replace('_', ' ')} specialist will follow up with you shortly to assist further."
            ),
            "justification": (
                "Escalated because this request involves account-specific, billing, or "
                "sensitive details that cannot be safely resolved from the public support corpus alone."
                + (f" Handled multiple intents: {', '.join(intents)} (prioritized highest risk)." if len(intents) > 1 else "")
            ),
            "request_type": request_type,
            "confidence_score": 1.0,
        }

    return {
        "status": "replied",
        "product_area": product_area,
        "response": (
                "Here is the relevant guidance from our support documentation:\n\n"
                f"{ _sanitize_excerpt(top_match.excerpt) }"
        ),
        "justification": (
            f"Answered directly using the official {company} support article: {top_match.title}."
            + (f" Handled multiple intents: {', '.join(intents)} (combined response)." if len(intents) > 1 else "")
        ),
        "request_type": request_type,
        "confidence_score": 1.0,
    }


def _extract_retry_delay_seconds(message: str) -> float | None:
    match = re.search(r"Please retry in ([0-9.]+)(ms|s)", message)
    if match:
        value = float(match.group(1))
        return value / 1000.0 if match.group(2) == "ms" else value

    match = re.search(r"'retryDelay': '([0-9.]+)s'", message)
    if match:
        return float(match.group(1))

    return None


def _is_daily_quota_error(message: str) -> bool:
    lowered = message.lower()
    return "perday" in lowered or "generaterequestsperday" in lowered or "quota exceeded" in lowered and "quotavalue': '20'" in lowered


def _respect_request_spacing() -> None:
    global _LAST_REQUEST_AT
    elapsed = time.monotonic() - _LAST_REQUEST_AT
    wait_seconds = GEMINI_MIN_SECONDS_BETWEEN_REQUESTS - elapsed
    if wait_seconds > 0:
        time.sleep(wait_seconds)
    _LAST_REQUEST_AT = time.monotonic()


def _normalize_result(result: dict[str, str], fallback_product_area: str, fallback_request_type: str) -> dict[str, str]:
    status = str(result.get("status", "")).strip().lower()
    request_type = str(result.get("request_type", "")).strip().lower()
    response = str(result.get("response", "")).strip()
    justification = str(result.get("justification", "")).strip()
    product_area = _normalize_product_area(str(result.get("product_area", "")), fallback_product_area)
    
    try:
        confidence_score = float(result.get("confidence_score", 1.0))
    except (ValueError, TypeError):
        confidence_score = 1.0

    if status not in ALLOWED_STATUS:
        status = "escalated"
    if request_type not in ALLOWED_REQUEST_TYPES:
        request_type = fallback_request_type
    if not response:
        response = (
            "Thanks for contacting support. I could not safely produce a grounded answer, "
            "so I am escalating this for human review."
        )
    if not justification:
        justification = "Escalated because the model output was incomplete."

    return {
        "status": status,
        "product_area": product_area,
        "response": response,
        "justification": justification,
        "request_type": request_type,
        "confidence_score": confidence_score,
    }


def fallback_agent_response(
    *,
    issue: str,
    subject: str,
    company: str,
    retrieval_result: RetrievalResult,
    request_type: str,
    failure_reason: str,
    intents: list[str] = None,
) -> dict[str, str]:
    return _fallback_from_retrieval(
        issue=issue,
        subject=subject,
        company=company,
        retrieval_result=retrieval_result,
        request_type=request_type,
        failure_reason=failure_reason,
        intents=intents,
    )


def generate_agent_response(
    *,
    issue: str,
    subject: str,
    company: str,
    retrieval_result: RetrievalResult,
    intents: list[str] = None,
) -> dict[str, str]:
    global _MODEL_DISABLED_REASON
    if intents is None:
        intents = []
    request_type = infer_request_type(issue=issue, subject=subject)
    fallback = lambda reason: fallback_agent_response(
        issue=issue,
        subject=subject,
        company=company,
        retrieval_result=retrieval_result,
        request_type=request_type,
        failure_reason=reason,
        intents=intents,
    )

    if _MODEL_DISABLED_REASON:
        return fallback(_MODEL_DISABLED_REASON)

    if not GEMINI_API_KEY:
        return fallback("GEMINI_API_KEY is missing.")

    try:
        from google import genai
    except ImportError:
        return fallback("google-genai is not installed.")

    client = genai.Client(api_key=GEMINI_API_KEY)
    last_error = "Unknown Gemini failure."
    for attempt in range(1, GEMINI_MAX_RETRIES + 1):
        try:
            _respect_request_spacing()
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=build_prompt(
                    issue=issue,
                    subject=subject,
                    company=company,
                    retrieval_result=retrieval_result,
                    intents=intents,
                ),
                config={
                    "temperature": 0.0,
                    "response_mime_type": "application/json",
                    "response_schema": RESPONSE_SCHEMA,
                },
            )
            parsed = _extract_json_block(response.text)
            break
        except Exception as exc:
            last_error = str(exc)
            if _is_daily_quota_error(last_error):
                _MODEL_DISABLED_REASON = "Gemini daily quota is exhausted for this project."
                return fallback(_MODEL_DISABLED_REASON)
            retry_delay = _extract_retry_delay_seconds(last_error)
            is_retryable = "429" in last_error or "RESOURCE_EXHAUSTED" in last_error
            if attempt >= GEMINI_MAX_RETRIES or not is_retryable:
                return fallback(last_error)
            time.sleep(max(retry_delay or GEMINI_MIN_SECONDS_BETWEEN_REQUESTS, 1.0))
    else:
        return fallback(last_error)

    return _normalize_result(
        parsed,
        fallback_product_area=retrieval_result.best_product_area,
        fallback_request_type=request_type,
    )
