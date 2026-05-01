from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from agent import generate_agent_response, fallback_agent_response, infer_request_type
from classifier import detect_company
from config import INPUT_CSV_PATH, OUTPUT_COLUMNS, OUTPUT_CSV_PATH
from direct_responder import try_direct_response
from retriever import retrieve_relevant_passages
from safety_gate import evaluate_safety
from multi_intent import extract_intents


def normalize_cell(value: object) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def build_escalation_row(
    *,
    issue: str,
    subject: str,
    company: str,
    product_area: str,
    response: str,
    justification: str,
    request_type: str,
    confidence_score: float = 1.0,
) -> dict[str, str]:
    return {
        "issue": issue,
        "subject": subject,
        "company": company,
        "response": response,
        "product_area": product_area,
        "status": "escalated",
        "request_type": request_type,
        "justification": justification,
        "confidence_score": confidence_score,
    }


def apply_post_processing(result: dict[str, str], intents: list[str]) -> dict[str, str]:
    """Applies global confidence scoring rules and multi-intent logging to any generated result row."""
    status = result.get("status", "")
    justification = result.get("justification", "")
    product_area = result.get("product_area", "")
    
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
            
    return result


def process_row(index: int, total_rows: int, row: pd.Series) -> dict[str, str]:
    issue = normalize_cell(row.get("Issue", ""))
    subject = normalize_cell(row.get("Subject", ""))
    original_company = normalize_cell(row.get("Company", ""))

    print(f"[{index}/{total_rows}] Processing ticket for subject: {subject or '(no subject)'}")

    company = detect_company(issue=issue, subject=subject, company_value=original_company)
    request_type = infer_request_type(issue=issue, subject=subject)
    
    # Extract intents
    intents = extract_intents(f"{subject} {issue}")
    
    safety_result = evaluate_safety(issue=issue, subject=subject, company=company)

    if safety_result.is_dangerous:
        escalation_response = safety_result.response or (
            "Thanks for contacting support. This request needs specialist review, "
            "so I am escalating it to the appropriate team."
        )
        return apply_post_processing(build_escalation_row(
            issue=issue,
            subject=subject,
            company=company,
            product_area=safety_result.product_area,
            response=escalation_response,
            justification=safety_result.justification,
            request_type=safety_result.request_type or request_type,
            confidence_score=safety_result.confidence_score,
        ), intents)

    direct_response = try_direct_response(issue=issue, subject=subject, company=company)
    if direct_response is not None:
        return apply_post_processing({
            "issue": issue,
            "subject": subject,
            "company": company,
            "response": direct_response.response,
            "product_area": direct_response.product_area,
            "status": direct_response.status,
            "request_type": direct_response.request_type,
            "justification": direct_response.justification,
            "confidence_score": direct_response.confidence_score,
        }, intents)

    retrieval_result = retrieve_relevant_passages(issue=issue, subject=subject, company=company)
    resolved_company = company if company != "Unknown" else retrieval_result.company

    if not retrieval_result.matches or retrieval_result.matches[0].score <= 0:
        return apply_post_processing(build_escalation_row(
            issue=issue,
            subject=subject,
            company=resolved_company,
            product_area=retrieval_result.best_product_area,
            response=(
                f"Thanks for reaching out to {resolved_company} support. "
                "We could not automatically resolve this request from the available documentation, "
                "so a specialist will follow up with you shortly."
            ),
            justification=(
                "Escalated because retrieval did not find any support article "
                "match in the provided corpus for this issue."
            ),
            request_type=request_type,
            confidence_score=1.0,
        ), intents)

    agent_result = generate_agent_response(
        issue=issue,
        subject=subject,
        company=resolved_company,
        retrieval_result=retrieval_result,
        intents=intents,
    )
    agent_result.setdefault("request_type", request_type)

    if agent_result.get("status") not in {"replied", "escalated"}:
        agent_result = fallback_agent_response(
            issue=issue,
            subject=subject,
            company=resolved_company,
            retrieval_result=retrieval_result,
            request_type=request_type,
            failure_reason="Model returned an invalid status.",
            intents=intents,
        )

    return apply_post_processing({
        "issue": issue,
        "subject": subject,
        "company": resolved_company,
        "response": agent_result["response"],
        "product_area": agent_result["product_area"],
        "status": agent_result["status"],
        "request_type": agent_result["request_type"],
        "justification": agent_result["justification"],
        "confidence_score": agent_result["confidence_score"],
    }, intents)


def run_pipeline(input_csv_path: Path, output_csv_path: Path) -> None:
    if not input_csv_path.exists():
        raise FileNotFoundError(f"Input CSV not found: {input_csv_path}")

    tickets = pd.read_csv(input_csv_path)
    results = [process_row(index + 1, len(tickets), row) for index, row in tickets.iterrows()]

    output_csv_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(results).reindex(columns=OUTPUT_COLUMNS).to_csv(output_csv_path, index=False)

    print(f"Done. {output_csv_path.name} saved.")


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
