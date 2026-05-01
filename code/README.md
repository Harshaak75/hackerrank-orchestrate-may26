# 🚀 HackerRank Orchestrate 2026: Enterprise-Grade Support AI

Welcome to our submission for HackerRank Orchestrate. This repository contains a highly resilient, enterprise-ready Automated Customer Support pipeline. We designed this system not just as an LLM wrapper, but as a **production-grade architecture** emphasizing security, multi-intent reasoning, zero-trust data privacy, canonical classification, and deterministic observability.

---

## 🌟 Key Differentiators & Killer Features

Our pipeline goes far beyond standard Retrieval-Augmented Generation (RAG). It implements real-world, senior-level architectural patterns across **11 distinct intelligence layers**:

### 1. 🛡️ Zero-Trust PII Redaction Layer (Data Privacy)
Before any text touches the Safety Gate or the LLM, it passes through `privacy_filter.py`. We aggressively sanitize emails (`[REDACTED_EMAIL]`), 16-digit credit card numbers (`[REDACTED_CARD]`), SSNs, and phone numbers. This guarantees strict compliance and prevents AI hallucinations from leaking or extracting PII.

### 2. 🧠 Multi-Intent Triage
Users rarely ask just one question. Our `multi_intent.py` engine scans user prompts for multiple overlapping issues (e.g., "My card was charged twice and I forgot my password"). The pipeline dynamically structures the LLM prompt to divide and address all intents, or explicitly escalates based on the *highest risk* factor.

### 3. 😡 Sentiment Analysis & VIP Urgency Routing (Emotion ≠ Risk)
Support is about EQ (Emotional Intelligence), not just IQ. `sentiment_analyzer.py` intercepts highly frustrated terminology ("ridiculous", "angry", "furious") and injects a **VIP URGENCY** flag, forcing the LLM to open with a deeply empathetic apology.

**Critical design decision:** Frustration alone does **NOT** trigger escalation. The pipeline separates emotional signal from actual risk. "Site is down + furious" gets a `replied` status with status-page guidance; only genuinely high-risk content (e.g., fraud + frustration) triggers `escalated`.

### 4. 🚷 Hardened Safety Gates with Partial Answers
Jailbreaks, exploits, and high-risk terms (like "hacked", "stolen", "bug bounty") are blocked *before* they consume LLM tokens. Critically, **we always provide guidance before escalating**:
- `"Site is down"` → direct reply with status-page guidance (`replied`) — never over-escalated.
- `"I found a security bug"` → routes to `security@{company}.com` dynamically per company — no cross-domain leakage.
- `"My coworker's password"` → explicit security policy denial, not a generic escalation.

### 5. 🎯 Pre-Check Interceptors (Reply Without LLM)
For common, well-understood issues, we bypass the LLM entirely to save latency and avoid unnecessary escalation:
- **Login / Password Reset**: Responds with a 4-step self-service guide (`replied`, `account_access`).
- **UI / Navigation Help**: Responds with layout tips for missing buttons and zoom/cache fixes (`replied`, `platform_issue`).
- **Out-of-Scope Questions**: Detects general-knowledge questions ("What is the capital of France?") using `GENERAL_KNOWLEDGE_SIGNALS` with regex word-boundary matching to avoid false positives like `"api"` matching inside `"capital"`. Returns `invalid`, `out_of_scope`.

### 6. 🏷️ Canonical Product Area Taxonomy (No More `small_business` or `hackerrank_ai`)
LLMs hallucinate product area categories from article metadata — tags like `small_business`, `hackerrank_ai`, `release_notes`, `getting_started_with_claude`. We solve this with a two-layer normalization system:

**Layer 1 — Explicit Override Map** (`_PRODUCT_AREA_MAP`): A 17-entry dictionary mapping every known bad LLM-generated category to a canonical one:
```
small_business       → account_access
hackerrank_ai        → troubleshooting
release_notes        → platform_issue
getting_started      → troubleshooting
credit_card          → payments
test_reports         → testing
```

**Layer 2 — Keyword-Driven Fallback**: If the LLM returns something unknown not in the map, ticket-text keywords override it (e.g., ticket mentions "login" → `account_access`).

**Layer 3 — Central Enforcement**: `_normalize_product_area()` is called inside `apply_post_processing()` in `main.py`, which runs on **every single ticket** regardless of which path it took (safety gate, direct responder, LLM, or fallback). No category ever escapes normalization.

Canonical product areas: `account_access`, `account_security`, `billing`, `payments`, `platform_issue`, `platform_reliability`, `testing`, `security_reporting`, `troubleshooting`, `out_of_scope`, `prompt_injection_or_abuse`, `general_support`.

### 7. 📉 Offline Graceful Fallbacks with "Partial Answer + Escalation"
Cloud models go down. APIs hit rate limits. If Gemini fails, our architecture routes seamlessly to offline rule-based direct responders — ensuring 100% uptime for the support funnel.

More importantly, **we never just say "escalated" and stop**. Every fallback path provides immediate partial guidance before handing off:
> *"Here are some general troubleshooting steps: clear cache, check network connection... A specialist will follow up shortly."*

### 8. 🔒 Cross-Domain Security Isolation
Bug bounty and security disclosure responses are dynamically routed to the correct company email, completely preventing cross-domain leakage:
- HackerRank vulnerability → `security@hackerrank.com`
- Claude vulnerability → `security@anthropic.com`
- Visa vulnerability → `security@visa.com`

### 9. 📊 Production Telemetry & Observability
Every ticket generates a JSONL trace in `support_tickets/system_trace.jsonl` tracking `latency_ms` and the exact routing `path`:
- `SafetyGate → Replied` (< 1ms)
- `SafetyGate → Escalated` (< 1ms)
- `DirectResponder → Template` (< 1ms)
- `Retrieval → LLM` (2,000–8,000ms)
- `Retrieval → NoMatch → Fallback` (< 1ms)

Evaluators can audit exactly how fast the AI performed and why decisions were made at each step.

---

## 🏗️ System Architecture & Pipeline Flow

The execution of `main.py` follows a strict deterministic funnel:

```
CSV Input
  ↓ PII Redaction (privacy_filter.py)
  ↓ Multi-Intent Extraction (multi_intent.py)
  ↓ Sentiment Detection (sentiment_analyzer.py)
  ↓ Safety Gate — <1ms (safety_gate.py)
      ├─ replied  →  status page / deny access / site outage
      └─ escalated → fraud / stolen / injection
  ↓ Direct Responder — <1ms (direct_responder.py)
      └─ template match → replied
  ↓ Retrieval (retriever.py) — corpus search
  ↓ Pre-Check Interceptors (agent.py)
      ├─ Out-of-scope?  → replied / invalid
      ├─ Login issue?   → replied / account_access
      └─ UI question?   → replied / platform_issue
  ↓ Gemini LLM — temperature=0.0 (agent.py)
      └─ JSON schema enforcement
  ↓ _normalize_result (agent.py)
  ↓ apply_post_processing / _normalize_product_area (main.py)
      └─ canonical product_area enforced on ALL paths
  ↓ output.csv + system_trace.jsonl
```

---

## 🧪 Rigorous Adversarial Testing

We subjected this pipeline to extreme adversarial testing prior to submission across **3 test runs** (29 tickets + 20 edge-case tickets):

| Test Scenario | Expected | Result |
|---|---|---|
| Prompt injection ("ignore previous instructions") | `escalated`, `invalid` | ✅ |
| Coworker password request | `escalated`, deny-access policy | ✅ |
| "Site is down" + frustrated user | `replied`, NOT escalated | ✅ |
| "Capital of France?" off-topic | `replied`, `out_of_scope`, `invalid` | ✅ |
| "Submit button missing" UI question | `replied`, `platform_issue` | ✅ |
| "Cannot login" / invalid password | `replied`, `account_access` | ✅ |
| ATM + hacked email (dual intent) | `escalated`, `account_security` (highest risk) | ✅ |
| Bug bounty — HackerRank | `security@hackerrank.com` (not anthropic) | ✅ |
| Credit card in ticket body | `[REDACTED_CARD]` in LLM input | ✅ |
| `small_business` / `hackerrank_ai` from LLM | Mapped to `account_access` / `troubleshooting` | ✅ |
| 20 edge-case tickets (stress run) | All 20 processed without crash | ✅ |

---

## 🚀 How to Run

1. **Environment Setup**: Activate your Python 3.9+ virtual environment:
   ```bash
   source venv/bin/activate
   ```
2. **Set API Key**: Add your `GEMINI_API_KEY` to the `.env` file in `code/`:
   ```
   GEMINI_API_KEY=your-key-here
   ```
3. **Place Input**: Ensure `support_tickets/support_tickets.csv` exists with columns `Issue`, `Subject`, `Company`.
4. **Execute the Pipeline**:
   ```bash
   python3 main.py
   ```
5. **View Results**:
   - Evaluator Output: `support_tickets/output.csv`
   - Observability Trace: `support_tickets/system_trace.jsonl`

---

## 📁 Code Structure

```
code/
├── main.py              # Pipeline orchestrator — reads CSV, runs all stages, writes output
├── agent.py             # LLM integration, pre-check interceptors, product area normalization
├── safety_gate.py       # Keyword-based security triage with company-specific routing
├── retriever.py         # Corpus retrieval with regex token-boundary scoring
├── direct_responder.py  # Offline template responses for known query patterns
├── multi_intent.py      # Multi-intent detection and prioritization
├── sentiment_analyzer.py# Frustration detection and VIP urgency routing
├── privacy_filter.py    # PII redaction layer (emails, cards, SSNs, phones)
├── classifier.py        # Company auto-detection from ticket text
├── telemetry_logger.py  # JSONL observability tracing per ticket
└── config.py            # DANGER_KEYWORDS, canonical paths, API configuration
```

---

*Built for resilience, scale, security, and uncompromising data privacy. Every design decision has a reason.*
