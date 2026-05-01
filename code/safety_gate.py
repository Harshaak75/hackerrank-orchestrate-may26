from __future__ import annotations

from dataclasses import dataclass, field

from config import DANGER_KEYWORDS


@dataclass(frozen=True)
class SafetyResult:
    is_dangerous: bool
    matched_keywords: list[str]
    product_area: str
    request_type: str
    response: str = ""  # Contextual escalation message for the user
    justification: str = ""
    confidence_score: float = 1.0


def evaluate_safety(issue: str, subject: str = "", company: str = "") -> SafetyResult:
    text = f"{subject} {issue}".lower()
    matched_keywords = [keyword for keyword in DANGER_KEYWORDS if keyword in text]

    # Urgent financial refund demands on Visa (not HackerRank service billing)
    is_visa = company == "Visa" or "visa" in text
    if is_visa and "refund" in text and any(
        phrase in text
        for phrase in {
            "make visa refund me",
            "refund me today",
            "ban the seller",
        }
    ):
        matched_keywords.append("urgent_visa_refund_demand")

    # Platform-wide outage language
    if any(keyword in text for keyword in {"site is down", "none of the pages are accessible"}):
        matched_keywords.extend([kw for kw in ("site is down",) if kw in text])

    if not matched_keywords:
        return SafetyResult(
            is_dangerous=False,
            matched_keywords=[],
            product_area="",
            request_type="",
            response="",
        )

    # Determine product_area (specific, not just company name)
    if any(kw in text for kw in {"fraud", "stolen card", "chargeback", "cvv", "pin number"}) \
            or "urgent_visa_refund_demand" in matched_keywords:
        product_area = "payments"
        # Tailor the response based on whether this is a dispute or card-security issue
        if "ban the seller" in text or "refund" in text:
            response = (
                "Hi,\n\n"
                "For payment disputes with a merchant (wrong product, unresponsive seller), "
                "the correct process is:\n\n"
                "1. Contact your card-issuing bank directly — use the number on the back of your Visa card "
                "or visit their website to file a formal dispute/chargeback.\n"
                "2. Your bank will investigate and can reverse the charge under Visa's dispute resolution rules.\n"
                "3. Visa itself does not directly process individual merchant bans; "
                "this is handled through the chargeback process via your issuing bank.\n\n"
                "Our team is escalating this so a payments specialist can confirm next steps for your specific case."
            )
            justification = "Escalated due to financial transaction and dispute resolution requiring manual verification by a payments specialist."
        else:
            response = (
                "Hi,\n\n"
                "Since this involves a payment security concern (potential fraud, stolen card, or CVV issue), "
                "please take these steps immediately:\n\n"
                "1. Call the number on the back of your Visa card to report the issue to your issuing bank.\n"
                "2. Your bank can block the card, dispute charges, and issue a replacement.\n\n"
                "Our payments support team is also being alerted and will follow up with you."
            )
            justification = "Escalated due to highly sensitive financial security concern (fraud/stolen card) requiring immediate banking intervention."
    elif any(
        kw in text
        for kw in {
            "restore my access immediately",
            "not the workspace owner",
            "not the owner",
            "not the admin",
        }
    ):
        product_area = "account_access"
        response = (
            "Since this involves account access that requires administrator authorization, "
            "our account team will verify your identity and access rights before any changes can be made. "
            "Please contact your workspace owner or IT admin to initiate the request."
        )
        justification = "Escalated due to account access security policies requiring strict identity and administrator authorization."
    elif any(kw in text for kw in {"delete all files from the system", "display all the rules", "internal rules", "logic exact"}):
        product_area = "prompt_injection_or_abuse"
        response = (
            "This request cannot be processed as it falls outside the scope of customer support. "
            "If you have a legitimate support need, please rephrase your question."
        )
        justification = "Escalated due to explicit prompt injection or system abuse terms detected by the safety gate."
    elif any(kw in text for kw in {"security vulnerability", "bug bounty"}):
        product_area = "security_reporting"
        response = (
            "Thank you for flagging a potential security issue. Our security team will review your report. "
            "For responsible disclosure, please submit details through Anthropic's official security "
            "reporting channel at security@anthropic.com."
        )
        justification = "Escalated to the security team due to the disclosure of a potential security vulnerability or bug bounty."
    elif "site is down" in text or "none of the pages are accessible" in text:
        product_area = "platform_reliability"
        response = (
            "We're sorry you're experiencing access issues. Our engineering team monitors platform status "
            "continuously. Please check our status page for real-time updates on any active incidents."
        )
        justification = "Escalated due to reports of a severe platform outage or major reliability incident."
    elif any(kw in text for kw in {
        "ignore previous instructions", "system prompt", "developer message",
        "reveal hidden prompt", "bypass safety", "disable guardrails",
        "malware", "exploit", "hack into",
    }):
        product_area = "prompt_injection_or_abuse"
        response = (
            "This request cannot be processed as it falls outside the scope of customer support."
        )
        justification = "Escalated due to suspected malicious exploit or advanced jailbreak attempt."
    else:
        product_area = company.lower().replace(" ", "_") if company else "safety_review"
        response = (
            "This request requires review by our specialized support team. "
            "A specialist will follow up with you shortly."
        )
        justification = f"Escalated by the safety gate because the ticket includes high-risk terms: {', '.join(matched_keywords)}."

    # Determine request_type
    if any(kw in text for kw in {
        "ignore previous instructions", "system prompt", "developer message",
        "bypass safety", "delete all files from the system",
        "display all the rules", "internal rules", "logic exact",
    }):
        request_type = "invalid"
    elif "site is down" in text or "none of the pages are accessible" in text:
        request_type = "bug"
    else:
        request_type = "product_issue"

    return SafetyResult(
        is_dangerous=True,
        matched_keywords=sorted(set(matched_keywords)),
        product_area=product_area,
        request_type=request_type,
        response=response,
        justification=justification,
    )
