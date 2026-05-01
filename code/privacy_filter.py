import re

def redact_pii(text: str) -> str:
    """
    Zero-Trust PII Redaction Layer.
    Intercepts and masks personally identifiable information (PII) before it reaches any LLM.
    """
    if not text:
        return text

    # 1. Redact Emails
    email_pattern = r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+"
    text = re.sub(email_pattern, "[REDACTED_EMAIL]", text)

    # 2. Redact Credit Card Numbers (16 digits with optional spaces/dashes)
    cc_pattern = r"\b(?:\d{4}[-\s]?){3}\d{4}\b"
    text = re.sub(cc_pattern, "[REDACTED_CARD]", text)

    # 3. Redact Social Security Numbers (XXX-XX-XXXX)
    ssn_pattern = r"\b\d{3}-\d{2}-\d{4}\b"
    text = re.sub(ssn_pattern, "[REDACTED_SSN]", text)

    # 4. Redact Phone Numbers (US/International standard formats)
    phone_pattern = r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"
    text = re.sub(phone_pattern, "[REDACTED_PHONE]", text)

    return text
