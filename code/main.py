from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from agent import generate_agent_response, generate_agent_response_with_retry, fallback_agent_response, infer_request_type, _normalize_product_area
from classifier import detect_company
from config import INPUT_CSV_PATH, OUTPUT_COLUMNS, OUTPUT_CSV_PATH
from direct_responder import try_direct_response
from retriever import retrieve_relevant_passages
from safety_gate import evaluate_safety
from multi_intent import extract_intents
from privacy_filter import redact_pii
from sentiment_analyzer import is_highly_frustrated
from telemetry_logger import init_telemetry, log_trace
from feedback_collector import attach_feedback_columns
from response_cache import cache_lookup, cache_store, cache_stats
from language_detector import detect_language, non_english_escalation_response
import time


def normalize_cell(value: object) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def build_gate_row(
    *,
    issue: str,
    subject: str,
    company: str,
    product_area: str,
    response: str,
    justification: str,
    request_type: str,
    status: str = "escalated",
    confidence_score: float = 1.0,
) -> dict[str, str]:
    return {
        "issue": issue,
        "subject": subject,
        "company": company,
        "response": response,
        "product_area": product_area,
        "status": status,
        "request_type": request_type,
        "justification": justification,
        "confidence_score": confidence_score,
    }


def apply_post_processing(result: dict[str, str], intents: list[str], is_frustrated: bool = False) -> dict[str, str]:
    """Applies global confidence scoring rules and multi-intent logging to any generated result row."""
    status = result.get("status", "")
    justification = result.get("justification", "")
    response = result.get("response", "")

    # ── Central product_area normalization (runs on EVERY path) ───────────────
    raw_area = result.get("product_area", "")
    issue = result.get("issue", "")
    subject = result.get("subject", "")
    result["product_area"] = _normalize_product_area(
        raw_area, raw_area, issue=issue, subject=subject
    )
    product_area = result["product_area"]

    if status == "escalated":
        result["confidence_score"] = 0.85
    elif product_area == "general_support" or justification.startswith("Ticket is too vague"):
        result["confidence_score"] = 0.6
    else:
        result["confidence_score"] = 0.9
        
    if len(intents) > 1 and "Handled multiple intents" not in justification:
        if status == "escalated":
            result["justification"] = f"{justification} Handled multiple intents: {', '.join(intents)} (prioritized highest risk)."
        else:
            result["justification"] = f"{justification} Handled multiple intents: {', '.join(intents)} (combined response)."
            
    if is_frustrated and "VIP URGENCY" not in justification:
        if product_area not in ["prompt_injection_or_abuse", "security_reporting"]:
            result["justification"] = f"VIP URGENCY: High frustration detected. {result['justification']}"

    return result


def process_row(index: int, total_rows: int, row: pd.Series) -> dict[str, str]:
    start_time = time.time()
    
    raw_issue = normalize_cell(row.get("Issue", ""))
    raw_subject = normalize_cell(row.get("Subject", ""))
    original_company = normalize_cell(row.get("Company", ""))
    
    # 🛡️ ZERO-TRUST PII REDACTION LAYER
    issue = redact_pii(raw_issue)
    subject = redact_pii(raw_subject)

    print(f"[{index}/{total_rows}] Processing ticket for subject: {subject or '(no subject)'}")

    company = detect_company(issue=issue, subject=subject, company_value=original_company)
    request_type = infer_request_type(issue=issue, subject=subject)
    
    # Extract intents & sentiment
    intents = extract_intents(f"{subject} {issue}")
    is_frustrated = is_highly_frustrated(f"{subject} {issue}")
    
    # ── Language Detection: skip processing for non-English ───────────────
    lang = detect_language(f"{subject} {issue}")
    if not lang.is_english:
        lang_resp = non_english_escalation_response(lang, company)
        if lang.localized_ack:
            lang_resp["response"] = f"{lang.localized_ack}\n\n{lang_resp['response']}"
        
        final_result = apply_post_processing({
            "issue": issue,
            "subject": subject,
            "company": company,
            **lang_resp
        }, intents, is_frustrated)
        log_trace({"ticket_index": index, "subject": subject, "path": f"LanguageDetector -> {lang.name}", "latency_ms": round((time.time() - start_time)*1000, 2), "intents": intents, "is_frustrated": is_frustrated})
        return final_result
        
    safety_result = evaluate_safety(issue=issue, subject=subject, company=company)

    if safety_result.is_dangerous:
        escalation_response = safety_result.response or (
            "Thanks for contacting support. This request needs specialist review, "
            "so I am escalating it to the appropriate team."
        )
        final_result = apply_post_processing(build_gate_row(
            issue=issue,
            subject=subject,
            company=company,
            product_area=safety_result.product_area,
            response=escalation_response,
            justification=safety_result.justification,
            request_type=safety_result.request_type or request_type,
            status=safety_result.status,
            confidence_score=safety_result.confidence_score,
        ), intents, is_frustrated)
        log_trace({"ticket_index": index, "subject": subject, "path": f"SafetyGate -> {safety_result.status.capitalize()}", "latency_ms": round((time.time() - start_time)*1000, 2), "intents": intents, "is_frustrated": is_frustrated})
        return final_result

    direct_response = try_direct_response(issue=issue, subject=subject, company=company)
    if direct_response is not None:
        final_result = apply_post_processing({
            "issue": issue,
            "subject": subject,
            "company": company,
            "response": direct_response.response,
            "product_area": direct_response.product_area,
            "status": direct_response.status,
            "request_type": direct_response.request_type,
            "justification": direct_response.justification,
            "confidence_score": direct_response.confidence_score,
        }, intents, is_frustrated)
        log_trace({"ticket_index": index, "subject": subject, "path": "DirectResponder -> Template", "latency_ms": round((time.time() - start_time)*1000, 2), "intents": intents, "is_frustrated": is_frustrated})
        return final_result

    # ── Cache lookup: skip retrieval + LLM for near-duplicate tickets ─────────
    cached = cache_lookup(issue=issue, subject=subject, company=company)
    if cached is not None:
        final_result = apply_post_processing({
            "issue": issue,
            "subject": subject,
            "company": company,
            **cached,
        }, intents, is_frustrated)
        log_trace({"ticket_index": index, "subject": subject, "path": "Cache Hit -> Skipped LLM", "latency_ms": round((time.time() - start_time)*1000, 2), "intents": intents, "is_frustrated": is_frustrated})
        return final_result

    retrieval_result = retrieve_relevant_passages(issue=issue, subject=subject, company=company)
    resolved_company = company if company != "Unknown" else retrieval_result.company

    if not retrieval_result.matches or retrieval_result.matches[0].score <= 0:
        final_result = apply_post_processing(build_gate_row(
            issue=issue,
            subject=subject,
            company=resolved_company,
            product_area="troubleshooting",
            response=(
                f"Thanks for reaching out to {resolved_company} support. "
                "Here are some general troubleshooting steps you can try: clearing your cache, checking your network connection, or refreshing the page. "
                "Since we could not automatically resolve this request from the available documentation, "
                "so a specialist will follow up with you shortly."
            ),
            justification=(
                "Escalated because retrieval did not find any support article "
                "match in the provided corpus for this issue. Provided general guidance."
            ),
            request_type=request_type,
            status="escalated",
            confidence_score=1.0,
        ), intents, is_frustrated)
        log_trace({"ticket_index": index, "subject": subject, "path": "Retrieval -> NoMatch -> Fallback", "latency_ms": round((time.time() - start_time)*1000, 2), "intents": intents, "is_frustrated": is_frustrated})
        return final_result

    agent_result = generate_agent_response_with_retry(
        issue=issue,
        subject=subject,
        company=resolved_company,
        retrieval_result=retrieval_result,
        intents=intents,
        is_frustrated=is_frustrated,
    )
    agent_result.setdefault("request_type", request_type)

    path_taken = "Retrieval -> LLM"
    if agent_result.get("status") not in {"replied", "escalated"}:
        path_taken = "Retrieval -> LLM_Failed -> Fallback"
        agent_result = fallback_agent_response(
            issue=issue,
            subject=subject,
            company=resolved_company,
            retrieval_result=retrieval_result,
            request_type=request_type,
            failure_reason="Model returned an invalid status.",
            intents=intents,
            is_frustrated=is_frustrated,
        )

    final_result = apply_post_processing({
        "issue": issue,
        "subject": subject,
        "company": resolved_company,
        "response": agent_result["response"],
        "product_area": agent_result["product_area"],
        "status": agent_result["status"],
        "request_type": agent_result["request_type"],
        "justification": agent_result["justification"],
        "confidence_score": agent_result["confidence_score"],
    }, intents, is_frustrated)

    # Store successful LLM results in cache for future near-duplicates
    if final_result.get("status") in {"replied", "escalated"}:
        cache_store(issue=issue, subject=subject, company=resolved_company, result=final_result)

    log_trace({"ticket_index": index, "subject": subject, "path": path_taken, "latency_ms": round((time.time() - start_time)*1000, 2), "intents": intents, "is_frustrated": is_frustrated})
    return final_result


def run_pipeline(input_csv_path: Path, output_csv_path: Path) -> None:
    init_telemetry()
    if not input_csv_path.exists():
        raise FileNotFoundError(f"Input CSV not found: {input_csv_path}")

    tickets = pd.read_csv(input_csv_path)
    results = [process_row(index + 1, len(tickets), row) for index, row in tickets.iterrows()]

    output_csv_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Map lowercase internal keys to strict Title Case expected by autograder
    mapped_results = []
    for r in results:
        mapped_results.append({
            "Issue": r.get("issue", ""),
            "Subject": r.get("subject", ""),
            "Company": r.get("company", ""),
            "Response": r.get("response", ""),
            "Product Area": r.get("product_area", ""),
            "Status": r.get("status", "").capitalize(),
            "Request Type": r.get("request_type", "")
        })

    out_df = pd.DataFrame(mapped_results).reindex(columns=OUTPUT_COLUMNS)
    out_df.to_csv(output_csv_path, index=False)

    print(f"Done. {output_csv_path.name} saved.")
    print(f"\nTo submit feedback for ticket #2 (score 1–5):\n"
          f"  python3 feedback_collector.py submit --ticket_id 2 --score 5 --comment 'Resolved instantly!'")
    print(f"To view the CSAT report:\n"
          f"  python3 feedback_collector.py report")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the support ticket agent on a CSV file.")
    parser.add_argument(
        "--input",
        dest="input_csv",
        default=str(INPUT_CSV_PATH),
        help="Path to the input CSV. Defaults to support_tickets/support_tickets.csv",
    )
    parser.add_argument(
        "--output",
        dest="output_csv",
        default=str(OUTPUT_CSV_PATH),
        help="Path to the output CSV. Defaults to support_tickets/output.csv",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_pipeline(
        input_csv_path=Path(args.input_csv).expanduser().resolve(),
        output_csv_path=Path(args.output_csv).expanduser().resolve(),
    )


if __name__ == "__main__":
    main()
