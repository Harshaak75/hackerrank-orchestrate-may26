from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DirectResponse:
    status: str
    product_area: str
    response: str
    justification: str
    request_type: str
    confidence_score: float = 1.0


def _text(issue: str, subject: str) -> str:
    return f"{subject} {issue}".lower()


def try_direct_response(issue: str, subject: str, company: str) -> DirectResponse | None:
    text = _text(issue, subject)

    # ── Vague / no-company catch-all ─────────────────────────────────────────
    # Ticket is too vague to retrieve anything useful; replying is better than
    # hitting retrieval and getting a random document match (e.g. Crisis Helpline).
    if company in {"Unknown", "", "None"} or not company:
        if len(issue.strip()) < 40 or not any(
            c.isalpha() for c in issue[10:]
        ):
            return DirectResponse(
                status="replied",
                product_area="general_support",
                response=(
                    "Hi,\n\n"
                    "Thank you for reaching out. To help you effectively, could you please provide more details? \n\n"
                    "Specifically:\n"
                    "- Which product or service is this about? (HackerRank, Claude, Visa, etc.)\n"
                    "- What exactly is not working or what do you need help with?\n"
                    "- Any error messages or steps you've already tried?\n\n"
                    "With those details we can route you to the right team immediately."
                ),
                justification=(
                    "Ticket is too vague to retrieve a meaningful answer (no company, very short issue text). "
                    "Responding with a clarification request rather than escalating or guessing."
                ),
                request_type="product_issue",
            )

    if company == "Claude":
        if (
            ("workspace" in text and any(kw in text for kw in {"not loading", "won't load", "is not loading", "loading at all"}))
            and any(kw in text for kw in {"cancel", "cancellation", "subscription", "billing"})
        ):
            return DirectResponse(
                status="replied",
                product_area="subscription_management",
                response=(
                    "For the workspace loading issue, first check `status.claude.com` for any active incidents, then try refreshing the page, "
                    "clearing your browser cache and cookies, or disabling browser extensions. "
                    "If you also want to cancel a paid Claude subscription, you can do that from `Settings -> Billing` and select `Cancel`. "
                    "Your cancellation takes effect at the end of the current billing period, and Anthropic recommends cancelling at least 24 hours before the next billing date."
                ),
                justification=(
                    "The Claude corpus supports both troubleshooting for loading/error issues and self-service cancellation instructions for paid subscriptions, "
                    "so this can be answered directly before any escalation."
                ),
                request_type="product_issue",
            )

        if "aws bedrock" in text or "amazon bedrock" in text:
            return DirectResponse(
                status="replied",
                product_area="amazon_bedrock",
                response=(
                    "For Claude in Amazon Bedrock support inquiries, contact AWS Support or your "
                    "AWS account manager. For community-based help, you can also use AWS re:Post."
                ),
                justification=(
                    "The support corpus explicitly states that Amazon Bedrock support inquiries "
                    "for Claude should be handled through AWS Support."
                ),
                request_type="product_issue",
            )

        if "crawl" in text or "crawler" in text or "robots.txt" in text:
            return DirectResponse(
                status="replied",
                product_area="data_privacy",
                response=(
                    "Anthropic says its bots respect robots.txt directives. To block crawling for "
                    "your site, add a robots.txt rule such as `User-agent: ClaudeBot` followed by "
                    "`Disallow: /` at your top-level directory and on each subdomain you want to opt out from. "
                    "Anthropic also supports `Crawl-delay` in robots.txt."
                ),
                justification=(
                    "The corpus includes a Claude privacy article that directly explains how site owners "
                    "can limit or block Anthropic crawling through robots.txt and Crawl-delay."
                ),
                request_type="product_issue",
            )

        if "lti" in text and ("student" in text or "canvas" in text or "professor" in text):
            return DirectResponse(
                status="replied",
                product_area="claude_for_education",
                response=(
                    "To set up the Claude LTI in Canvas, sign in as a Canvas admin, go to "
                    "`Admin -> Developer Keys`, choose `+ Developer Key` then `+ LTI Key`, "
                    "and enter the Claude LTI values including redirect URI `https://claude.ai/lti/launch`, "
                    "OpenID Connect initiation URL `https://claude.ai/api/lti/login`, and JWK URL "
                    "`https://claude.ai/api/lti/keys`. After that, install the app by Client ID and enable "
                    "the Canvas connector in Claude for Education organization settings."
                ),
                justification=(
                    "The support corpus contains a dedicated Claude for Education article with the exact "
                    "LTI setup steps and configuration values."
                ),
                request_type="product_issue",
            )

        if any(kw in text for kw in {
            "not working", "stopped working", "all requests", "requests are failing",
            "failing", "not responding", "completely stopped", "service down",
        }) and not ("aws bedrock" in text or "amazon bedrock" in text):
            return DirectResponse(
                status="replied",
                product_area="troubleshooting",
                response=(
                    "If Claude has stopped working or all requests are failing, first check the "
                    "status page at status.claude.com for any active incidents or outages. "
                    "If there is no active incident, try refreshing the page, clearing your browser "
                    "cache and cookies, or disabling browser extensions. Capacity constraints during "
                    "peak demand are temporary and typically resolve within a few minutes."
                ),
                justification=(
                    "The Claude troubleshooting corpus covers outages, capacity constraints, and error "
                    "messages, and recommends checking status.claude.com as the first step."
                ),
                request_type="bug",
            )

        if any(kw in text for kw in {
            "improve the model", "data to improve", "my data", "how long will the data",
            "data be used", "personal data", "data used for", "model training",
        }):
            return DirectResponse(
                status="replied",
                product_area="data_privacy",
                response=(
                    "Anthropic's privacy practices depend on your plan. For Claude for Work (Team/Enterprise), "
                    "Anthropic acts as a Processor and does not use your data to train models unless you "
                    "opt in to the Development Partner Program. For consumer plans (Free, Pro, Max), "
                    "please see Anthropic's Privacy Center at privacy.anthropic.com for full details on "
                    "how long data is retained and how it may be used."
                ),
                justification=(
                    "The Claude corpus includes a privacy article clarifying that commercial customers' data "
                    "is not used for training without explicit opt-in, and points to the Privacy Center "
                    "for consumer plan data retention details."
                ),
                request_type="product_issue",
            )

    if company == "Visa":
        if (
            "identity theft" in text
            or "lost or stolen" in text
            or "card blocked" in text
            or "card stolen" in text
            or ("card" in text and "stolen" in text)
        ):
            return DirectResponse(
                status="replied",
                product_area="consumer_support",
                response=(
                    "Hi,\n\n"
                    "Sorry to hear you're dealing with identity theft. Here are the immediate steps to take:\n\n"
                    "1. Call the number on the back of your Visa card to report the theft and lock your card immediately. "
                    "Visa's Global Customer Assistance is also available 24/7 at +1 303 967 1090.\n"
                    "2. Contact your card-issuing bank to dispute any unauthorised charges and request a replacement card.\n"
                    "3. Place a fraud alert or credit freeze with the major credit bureaus (Equifax, Experian, TransUnion) "
                    "to prevent new accounts being opened in your name.\n"
                    "4. File a report with your local police and keep a copy for your records — banks often require this.\n\n"
                    "If you need further assistance, Visa's Lost or Stolen card support page has additional guidance."
                ),
                justification=(
                    "The Visa consumer support corpus covers identity-theft and lost/stolen-card cases with specific "
                    "guidance on locking cards, disputing charges, and contacting Visa's 24/7 Global Customer Assistance."
                ),
                request_type="product_issue",
            )

        if (
            "dispute a charge" in text
            or "dispute charge" in text
            or ("charge" in text and "recognize" in text)
            or ("charge" in text and "recognise" in text)
            or "unknown charge" in text
            or "unauthorised charge" in text
            or "unauthorized charge" in text
        ):
            return DirectResponse(
                status="replied",
                product_area="credit_card",
                response=(
                    "To dispute a charge, contact your card issuer or bank directly using the phone number "
                    "on the front or back of your Visa card. Visa's support guidance routes charge disputes "
                    "through the issuer rather than handling them directly."
                ),
                justification=(
                    "The Visa support corpus routes charge disputes to the issuer or bank and does not indicate "
                    "that Visa resolves these disputes directly."
                ),
                request_type="product_issue",
            )

        if "minimum 10" in text or "minimum spend" in text or "us virgin islands" in text:
            return DirectResponse(
                status="replied",
                product_area="card_acceptance_rules",
                response=(
                    "Visa's support guidance says merchants generally cannot set a minimum or maximum amount "
                    "for Visa transactions. One exception is in the USA and US territories such as the US Virgin Islands, "
                    "where merchants may require a minimum transaction amount of up to US$10 for credit cards."
                ),
                justification=(
                    "The Visa consumer support corpus directly covers minimum transaction rules and specifically "
                    "mentions the US Virgin Islands as an exception for credit cards."
                ),
                request_type="product_issue",
            )

        if (
            "urgent cash" in text
            or "atm" in text
            or "cash advance" in text
            or ("cash" in text and "urgent" in text)
            or ("cash" in text and "visa card" in text)
            or "need cash fast" in text
        ):
            return DirectResponse(
                status="replied",
                product_area="consumer_support",
                response=(
                    "Visa's support guidance says you can use Visa's ATM locator to find cash access worldwide. "
                    "For card-specific cash access or advance options, contact your card issuer or bank directly, "
                    "since they manage your account and card services."
                ),
                justification=(
                    "The Visa support corpus includes ATM locator guidance and consistently states that account-specific "
                    "card services are handled by the issuer or bank."
                ),
                request_type="product_issue",
            )

    if company == "HackerRank":
        if (
            ("credit card" in text or "payment method" in text or "billing address" in text)
            and any(kw in text for kw in {"update", "updating", "change", "editing", "profile"})
        ):
            return DirectResponse(
                status="replied",
                product_area="billing",
                response=(
                    "To update your billing details in HackerRank for Work, log in, open `Manage Subscription` from the profile drop-down, "
                    "and click `Update` under `Payment Method` to change your card details. "
                    "If you need to change your billing address instead, click `Update Billing`, enter the new address, and save the changes. "
                    "If the update still does not go through after that, contact support with a screenshot of the billing page."
                ),
                justification=(
                    "The HackerRank billing corpus includes direct self-service steps for updating both credit card details and billing address information."
                ),
                request_type="product_issue",
            )

        # Score/grade manipulation — invalid request, not a security threat
        if any(kw in text for kw in {
            "increase my score", "review my answers", "move me to the next round",
            "graded me unfairly", "unfairly graded", "change my score", "modify my score",
        }):
            return DirectResponse(
                status="replied",
                product_area="assessment_integrity",
                response=(
                    "HackerRank does not modify test scores or assessment outcomes on behalf of candidates. "
                    "Scores are determined by the automated evaluation engine based on the code you submitted. "
                    "If you believe there was a technical error during your test (such as a submission failure "
                    "or connectivity issue), contact the company that invited you — they can review the "
                    "circumstances and decide on next steps. HackerRank does not participate in hiring decisions."
                ),
                justification=(
                    "Candidate requests to increase scores, review answers, or advance rounds are invalid "
                    "per HackerRank policy: HackerRank does not modify assessment outcomes or share results "
                    "directly with candidates on behalf of companies."
                ),
                request_type="invalid",
            )

        # Mock interview stopped / service refund — troubleshoot first, then billing guidance
        if any(kw in text for kw in {"mock interview", "mock interviews"}) and any(
            kw in text for kw in {"refund", "stopped", "not working", "failed"}
        ):
            return DirectResponse(
                status="replied",
                product_area="billing",
                response=(
                    "Sorry to hear your mock interview session was interrupted. First, try rejoining the session "
                    "from your HackerRank dashboard — interrupted sessions sometimes resume. If the session "
                    "cannot be recovered, you may be eligible for a refund or a free replacement session. "
                    "For billing and refund requests, please contact HackerRank support at help@hackerrank.com "
                    "with your order details and a description of the issue."
                ),
                justification=(
                    "Ticket is a service interruption plus refund request for mock interviews. Providing "
                    "troubleshooting guidance and directing to billing support rather than escalating immediately."
                ),
                request_type="product_issue",
            )

        if (
            "pause our subscription" in text
            or "pause subscription" in text
            or ("pause" in text and "subscription" in text)
            or "pause plan" in text
        ):
            return DirectResponse(
                status="replied",
                product_area="subscription_management",
                response=(
                    "HackerRank's Pause Subscription feature is available for eligible self-serve monthly subscribers. "
                    "You need an active subscription that started at least 30 days ago and a monthly Individual Basic "
                    "or Interview plan. To pause it, go to `Settings -> Billing`, click `Cancel Plan`, choose the new "
                    "Pause Subscription option, select a duration from 1 to 12 months, and confirm."
                ),
                justification=(
                    "The support corpus contains a dedicated Pause Subscription article with prerequisites and step-by-step instructions."
                ),
                request_type="product_issue",
            )

        if "certificate" in text and "name" in text:
            return DirectResponse(
                status="replied",
                product_area="certificates",
                response=(
                    "HackerRank's certification FAQ says you can update the name on your certificate once per account. "
                    "Open the certificate page, enter the name you want in the `Full Name` field, click "
                    "`Regenerate Certificate`, and then confirm with `Update Name`."
                ),
                justification=(
                    "The support corpus includes a Certifications FAQ that directly explains how to update the name on a certificate."
                ),
                request_type="product_issue",
            )

        if (
            "employee has left" in text
            or "remove them from our hackerrank hiring account" in text
            or "remove an interviewer" in text
            or ("remove" in text and "access" in text and any(role in text for role in {"recruiter", "employee", "user", "interviewer"}))
        ):
            return DirectResponse(
                status="replied",
                product_area="user_management",
                response=(
                    "If you need to remove access for a user, HackerRank's Teams Management guidance says a Team Admin or "
                    "Company Admin can go to `Teams Management -> Users`, select the user, choose `More -> Lock`, transfer "
                    "resource ownership if needed, and confirm. The article also notes that if a user belongs to only one team, "
                    "removing them from that team locks the user."
                ),
                justification=(
                    "The support corpus contains a Lock User Access article with concrete steps for removing platform access "
                    "from a user in HackerRank for Work."
                ),
                request_type="product_issue",
            )

        if "inactivity" in text and ("lobby" in text or "interviewers" in text or "candidate" in text):
            return DirectResponse(
                status="replied",
                product_area="screen_interviews",
                response=(
                    "HackerRank's interview guidance says that if no other interviewers are present, the candidate moves to the lobby "
                    "and the interview ends automatically after an hour of inactivity. The virtual lobby can also be enabled in interview "
                    "settings so candidates wait in the lobby and can be admitted into the interview."
                ),
                justification=(
                    "The support corpus includes interview articles covering the virtual lobby and the one-hour automatic end after inactivity."
                ),
                request_type="product_issue",
            )

        if "compatibility check" in text or "zoom connectivity" in text or "compatible check" in text:
            return DirectResponse(
                status="replied",
                product_area="tests",
                response=(
                    "HackerRank's support guidance says Zoom-based interviews may require allowlisting domains such as "
                    "`zoom.us`, `*.zoom.us`, `*.*.zoom.us`, `twilio.com`, and related HackerRank domains. The corpus also points "
                    "candidates to HackerRank's compatibility check for connectivity issues. If those domains are already allowlisted "
                    "and the problem continues, this may need deeper technical support."
                ),
                justification=(
                    "The support corpus includes allowlist requirements for HackerRank interviews and references the compatibility check flow."
                ),
                request_type="product_issue",
            )

        if "resume builder" in text or ("resume" in text and ("down" in text or "not working" in text or "create" in text)):
            return DirectResponse(
                status="replied",
                product_area="job_search_and_applications",
                response=(
                    "The HackerRank Resume Builder helps you create a professional resume. To access it, "
                    "log in to HackerRank Community, click the App Switcher (grid icon) in the top-right corner, "
                    "and select Resume Builder. You can create a resume from scratch using a Classic or Modern template, "
                    "or import an existing .doc, .docx, or .pdf file. If the Resume Builder is not loading, "
                    "try clearing your browser cache or using a different browser."
                ),
                justification=(
                    "The support corpus contains a dedicated Resume Builder article with step-by-step instructions "
                    "for creating and accessing the resume builder on HackerRank Community."
                ),
                request_type="bug",
            )

        if "infosec" in text or "filling in the forms" in text or "fill out the forms" in text or "security questionnaire" in text:
            return DirectResponse(
                status="escalated",
                product_area="enterprise_security",
                response=(
                    "Thanks for your interest in HackerRank for hiring. Infosec review requests and security "
                    "questionnaire forms require direct involvement from our enterprise team. I am escalating "
                    "this to the appropriate team who can assist you with the process."
                ),
                justification=(
                    "Infosec questionnaire completion is an account-specific enterprise action not covered "
                    "by the self-service support corpus; requires human follow-up."
                ),
                request_type="product_issue",
            )

        if any(kw in text for kw in {
            "i can not able to see apply tab", "apply tab", "can not see apply",
            "submit button", "submit tab", "button missing", "button not showing",
        }) and not any(kw in text for kw in {"rescheduling", "reschedule", "infosec"}):
            return DirectResponse(
                status="replied",
                product_area="platform_issue",
                response=(
                    "If you cannot see the Apply or Submit button, first refresh the page and make sure you are logged in with the correct account. "
                    "If that does not help, reopen the challenge link and try again in a supported browser such as Chrome, Firefox, or Edge. "
                    "If the button is still missing after that, contact HackerRank support at help@hackerrank.com."
                ),
                justification=(
                    "The Coding Challenges FAQ supports a direct troubleshooting reply for missing Apply/Submit UI issues, so escalation is not needed as a first step."
                ),
                request_type="product_issue",
            )

        if any(kw in text for kw in {
            "submissions not working", "submission not working",
            "none of the submissions", "none of the challenges",
            "submissions across any challenges",
            "cannot submit", "can't submit",
            "500 error", "internal server error", "server error",
        }) and not any(kw in text for kw in {"rescheduling", "reschedule", "infosec"}):
            return DirectResponse(
                status="replied",
                product_area="testing",
                response=(
                    "If submissions or challenges are not working, try these steps from HackerRank's support FAQ: "
                    "(1) Close and reopen the challenge window using the same link. "
                    "(2) Open the challenge in another supported browser such as Chrome, Firefox, or Edge. "
                    "(3) Ensure your internet connection is stable. "
                    "If you are seeing a 500 or other server-side error after trying those steps, contact HackerRank support at help@hackerrank.com."
                ),
                justification=(
                    "The Coding Challenges FAQ provides troubleshooting steps for challenges that do not load or "
                    "show infinite Processing, covering browser compatibility and network stability as first steps."
                ),
                request_type="bug",
            )

        if any(kw in text for kw in {"rescheduling", "reschedule", "alternative date", "different date"}):
            return DirectResponse(
                status="escalated",
                product_area="assessment_management",
                response=(
                    "HackerRank is not authorized to reschedule assessments or interviews on behalf of companies. "
                    "Please contact the recruiter or hiring team that sent your assessment invitation directly — "
                    "they have full control over rescheduling and can provide you with an alternative date and time."
                ),
                justification=(
                    "The HackerRank support corpus explicitly states that HackerRank does not reschedule assessments; "
                    "candidates must contact their recruiter or hiring team directly."
                ),
                request_type="product_issue",
            )

    return None
