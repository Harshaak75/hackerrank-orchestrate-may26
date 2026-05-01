from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from config import COMPANY_DATA_DIRS, STOP_WORDS


@dataclass(frozen=True)
class SupportDocument:
    company: str
    path: Path
    title: str
    breadcrumb: str
    content: str


@dataclass(frozen=True)
class RetrievedMatch:
    company: str
    title: str
    breadcrumb: str
    excerpt: str
    path: str
    score: int


@dataclass(frozen=True)
class RetrievalResult:
    company: str
    best_breadcrumb: str
    best_product_area: str
    matches: list[RetrievedMatch]


def _tokenize(text: str) -> list[str]:
    return [
        token
        for token in re.findall(r"[a-z0-9]{2,}", text.lower())
        if token not in STOP_WORDS
    ]


def _parse_document(path: Path, company: str) -> SupportDocument:
    raw_text = path.read_text(encoding="utf-8")
    title = ""
    breadcrumbs: list[str] = []
    body = raw_text

    if raw_text.startswith("---"):
        parts = raw_text.split("---", 2)
        if len(parts) == 3:
            frontmatter = parts[1]
            body = parts[2]
            in_breadcrumbs = False
            for line in frontmatter.splitlines():
                stripped = line.strip()
                if stripped.startswith('title: "') and stripped.endswith('"'):
                    title = stripped[len('title: "') : -1]
                elif stripped == "breadcrumbs:":
                    in_breadcrumbs = True
                elif in_breadcrumbs and stripped.startswith('- "'):
                    breadcrumbs.append(stripped[3:-1])
                elif in_breadcrumbs and not stripped.startswith("- "):
                    in_breadcrumbs = False

    if not title:
        for line in body.splitlines():
            if line.startswith("# "):
                title = line[2:].strip()
                break

    if not breadcrumbs:
        relative_parts = path.relative_to(COMPANY_DATA_DIRS[company]).parts[:-1]
        breadcrumbs = [part.replace("-", " ") for part in relative_parts if part]

    breadcrumb = " > ".join(part.strip() for part in breadcrumbs if part.strip())
    return SupportDocument(
        company=company,
        path=path,
        title=title or path.stem,
        breadcrumb=breadcrumb,
        content=body.strip(),
    )


@lru_cache(maxsize=None)
def _load_documents_for_company(company: str) -> tuple[SupportDocument, ...]:
    base_dir = COMPANY_DATA_DIRS[company]
    documents = []
    for path in sorted(base_dir.rglob("*.md")):
        if path.name == "index.md":
            continue
        documents.append(_parse_document(path, company))
    return tuple(documents)


def _score_document(document: SupportDocument, tokens: list[str]) -> tuple[int, str]:
    unique_tokens = list(dict.fromkeys(tokens))
    patterns = {token: re.compile(rf"\b{token}\b") for token in unique_tokens}
    
    combined_text = f"{document.title}\n{document.breadcrumb}\n{document.content}".lower()
    title_text = document.title.lower()
    breadcrumb_text = document.breadcrumb.lower()
    path_text = document.path.as_posix().lower()
    
    score = 0
    for pat in patterns.values():
        score += min(len(pat.findall(title_text)), 3) * 6
        score += min(len(pat.findall(breadcrumb_text)), 3) * 4
        score += min(len(pat.findall(path_text)), 5) * 3
        score += min(len(pat.findall(combined_text)), 4)

    paragraphs = [
        paragraph.strip()
        for paragraph in re.split(r"\n\s*\n", document.content)
        if paragraph.strip() and not paragraph.strip().startswith("---")
    ]
    windows = []
    lines = [line.strip() for line in document.content.splitlines() if line.strip()]
    for index in range(len(lines)):
        window = " ".join(lines[index : index + 5]).strip()
        if window:
            windows.append(window)

    best_excerpt = ""
    best_excerpt_score = -1
    for paragraph in paragraphs:
        p_lower = paragraph.lower()
        paragraph_score = sum(len(pat.findall(p_lower)) for pat in patterns.values())
        if paragraph_score > best_excerpt_score:
            best_excerpt = paragraph
            best_excerpt_score = paragraph_score
            
    for window in windows:
        w_lower = window.lower()
        window_score = sum(len(pat.findall(w_lower)) for pat in patterns.values())
        if window_score > best_excerpt_score:
            best_excerpt = window
            best_excerpt_score = window_score

    if not best_excerpt:
        best_excerpt = document.content[:1000].strip()

    excerpt = re.sub(r"\s+", " ", best_excerpt).strip()[:2500]
    score += max(best_excerpt_score, 0) * 5
    score -= len(document.content) // 4000
    if document.title.lower() in {"hackerrank knowledge base", "claude help center"}:
        score -= 500
    return score, excerpt


def _normalize_product_area(breadcrumb: str, company: str) -> str:
    if breadcrumb:
        leaf = breadcrumb.split(">")[-1].strip().lower()
        return re.sub(r"[^a-z0-9]+", "_", leaf).strip("_") or company.lower()
    return company.lower()


def retrieve_relevant_passages(issue: str, subject: str = "", company: str = "Unknown") -> RetrievalResult:
    search_text = f"{subject} {issue}".strip()
    tokens = _tokenize(search_text)
    companies = [company] if company in COMPANY_DATA_DIRS else list(COMPANY_DATA_DIRS.keys())

    scored_matches: list[RetrievedMatch] = []
    for current_company in companies:
        for document in _load_documents_for_company(current_company):
            score, excerpt = _score_document(document, tokens)
            scored_matches.append(
                RetrievedMatch(
                    company=current_company,
                    title=document.title,
                    breadcrumb=document.breadcrumb,
                    excerpt=excerpt,
                    path=str(document.path),
                    score=score,
                )
            )

    ranked_matches = sorted(
        scored_matches,
        key=lambda item: (item.score, item.company == company, item.title),
        reverse=True,
    )[:3]

    best_match = ranked_matches[0] if ranked_matches else None
    best_company = best_match.company if best_match else (company if company != "Unknown" else "Unknown")
    best_breadcrumb = best_match.breadcrumb if best_match else ""
    best_product_area = _normalize_product_area(best_breadcrumb, best_company)

    return RetrievalResult(
        company=best_company,
        best_breadcrumb=best_breadcrumb,
        best_product_area=best_product_area,
        matches=ranked_matches,
    )
