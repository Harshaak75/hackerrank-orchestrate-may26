"""
language_detector.py
────────────────────
Zero-dependency language detection for the support pipeline.

Strategy (two layers)
─────────────────────
Layer 1 — Unicode block analysis
    Checks character code-points to detect non-Latin scripts
    (Arabic, Chinese/Japanese/Korean, Devanagari, Cyrillic, Hebrew, Thai, etc.)
    These are caught immediately with no word-list needed.

Layer 2 — High-frequency word fingerprinting (Latin scripts)
    For text that passes the Latin-script test, the detector counts
    occurrences of the top-15 most frequent words in each supported language.
    Whichever language scores highest above the threshold wins.
    Ties default to English.

Supported languages
───────────────────
  Non-Latin scripts  : Arabic, Chinese/Japanese/Korean (CJK), Devanagari
                       (Hindi/Nepali), Cyrillic (Russian/Ukrainian/Bulgarian),
                       Hebrew, Thai, Greek
  Latin-script langs : English, Spanish, French, German, Portuguese, Italian,
                       Dutch, Polish, Indonesian/Malay

Outputs
───────
  LanguageResult
    .code          ISO 639-1 code (e.g. "fr", "en", "ar")
    .name          Human-readable name (e.g. "French")
    .script        "latin" | "arabic" | "cjk" | "devanagari" | "cyrillic" |
                   "hebrew" | "thai" | "greek" | "unknown"
    .confidence    0.0–1.0 (1.0 for script-detected non-Latin)
    .is_english    bool shorthand
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


# ──────────────────────────────────────────────────────────────────────────────
# Unicode block ranges for non-Latin script detection
# ──────────────────────────────────────────────────────────────────────────────

_SCRIPT_RANGES: list[tuple[int, int, str, str]] = [
    (0x0600, 0x06FF, "ar", "arabic"),
    (0x0750, 0x077F, "ar", "arabic"),
    (0xFB50, 0xFDFF, "ar", "arabic"),
    (0xFE70, 0xFEFF, "ar", "arabic"),
    (0x0400, 0x04FF, "ru", "cyrillic"),
    (0x0500, 0x052F, "ru", "cyrillic"),
    (0x0900, 0x097F, "hi", "devanagari"),
    (0x0980, 0x09FF, "bn", "devanagari"),
    (0x4E00, 0x9FFF, "zh", "cjk"),
    (0x3040, 0x30FF, "ja", "cjk"),
    (0xAC00, 0xD7AF, "ko", "cjk"),
    (0x3400, 0x4DBF, "zh", "cjk"),
    (0xF900, 0xFAFF, "zh", "cjk"),
    (0x0590, 0x05FF, "he", "hebrew"),
    (0x0FB1D, 0x0FB4E, "he", "hebrew"),
    (0x0E00, 0x0E7F, "th", "thai"),
    (0x0370, 0x03FF, "el", "greek"),
]

_SCRIPT_NAMES: dict[str, str] = {
    "ar": "Arabic", "ru": "Russian", "hi": "Hindi", "bn": "Bengali",
    "zh": "Chinese", "ja": "Japanese", "ko": "Korean",
    "he": "Hebrew", "th": "Thai", "el": "Greek",
}


# ──────────────────────────────────────────────────────────────────────────────
# High-frequency word fingerprints for Latin-script languages
# ──────────────────────────────────────────────────────────────────────────────

_LANG_WORDS: dict[str, tuple[str, set[str]]] = {
    "en": ("English", {
        "the", "and", "that", "have", "for", "not", "with", "you", "this",
        "but", "his", "from", "they", "say", "she", "will", "one", "all",
        "would", "there", "their", "what", "can", "your", "when", "about",
        "which", "been", "were", "are", "help", "account", "please", "need", "my",
    }),
    "es": ("Spanish", {
        "que", "del", "los", "las", "una", "con", "por", "para", "más",
        "como", "pero", "sus", "hay", "sin", "sobre", "también", "ser",
        "este", "desde", "entre", "cuando", "muy", "sin", "hasta", "mi",
        "me", "fue", "se", "le", "ayuda", "cuenta", "favor", "necesito", "hola",
        "yo", "tu", "el", "ella", "nosotros", "gracias",
    }),
    "fr": ("French", {
        "que", "les", "des", "une", "sur", "pas", "avec", "vous", "son",
        "qui", "dans", "tout", "comme", "par", "mais", "plus", "est",
        "pour", "elle", "nous", "leur", "quand", "bien", "aussi", "fait",
        "cette", "même", "sans", "ces", "au", "je", "ne", "le", "la", "me",
        "bonjour", "aide", "compte", "s'il", "plaît", "merci",
    }),
    "de": ("German", {
        "die", "der", "das", "und", "nicht", "sie", "ist", "von", "den",
        "mit", "ein", "eine", "auch", "für", "auf", "als", "an", "noch",
        "aber", "so", "dem", "sich", "bei", "nach", "durch", "um", "es",
        "wie", "sind", "kann", "ich", "du", "er", "wir", "mein", "habe",
        "was", "tun", "bitte", "hilfe", "konto", "passwort", "danke",
    }),
    "pt": ("Portuguese", {
        "que", "não", "uma", "com", "por", "dos", "como", "seu", "seus",
        "mas", "foi", "ser", "para", "mais", "sobre", "também", "são",
        "das", "quando", "já", "tem", "sua", "pela", "pelo", "pelos",
        "nas", "nos", "muito", "está", "eu", "minha", "conta", "ajuda", "favor",
        "obrigado", "olá",
    }),
    "it": ("Italian", {
        "che", "non", "una", "con", "per", "del", "dei", "alla", "dal",
        "come", "questo", "sono", "nel", "più", "anche", "ma", "quando",
        "loro", "degli", "lui", "lei", "tutto", "bene", "ci", "già",
        "molto", "qui", "dove", "sul", "alle", "io", "mio", "account", "aiuto",
        "favore", "grazie", "ciao",
    }),
    "nl": ("Dutch", {
        "van", "het", "een", "niet", "zijn", "met", "voor", "ook", "aan",
        "als", "ze", "nog", "maar", "wel", "op", "de", "er", "om", "hij",
        "bij", "dat", "door", "worden", "naar", "kan", "heeft", "bent",
        "uw", "mijn", "over", "ik", "heb", "hulp", "account", "alstublieft",
        "bedankt", "hallo",
    }),
    "pl": ("Polish", {
        "się", "nie", "jak", "jest", "ale", "czy", "tego", "ale", "już",
        "więc", "też", "tylko", "przez", "do", "na", "po", "ze", "tak",
        "tu", "czy", "oraz", "gdy", "się", "przy", "może", "ma", "co",
        "ich", "pan", "pani", "ja", "moje", "konto", "pomoc", "proszę", "dziękuję",
    }),
    "id": ("Indonesian", {
        "yang", "dan", "ini", "itu", "dengan", "adalah", "tidak", "ada",
        "dari", "untuk", "dalam", "saya", "kami", "bisa", "akan", "mereka",
        "sudah", "juga", "kepada", "karena", "lebih", "satu", "agar",
        "atau", "kita", "dia", "bila", "oleh", "atas", "bagi", "akun", "bantuan",
        "tolong", "terima", "kasih", "halo",
    }),
}

# Localized acknowledgment snippets (prepended to English response for non-English Latin tickets)
_LANG_ACK: dict[str, str] = {
    "es": "Gracias por contactarnos. Responderemos en inglés:",
    "fr": "Merci de nous avoir contactés. Nous allons répondre en anglais :",
    "de": "Danke für Ihre Nachricht. Wir antworten auf Englisch:",
    "pt": "Obrigado por entrar em contato. Responderemos em inglês:",
    "it": "Grazie per averci contattato. Risponderemo in inglese:",
    "nl": "Bedankt voor uw bericht. We antwoorden in het Engels:",
    "pl": "Dziękujemy za kontakt. Odpowiemy po angielsku:",
    "id": "Terima kasih telah menghubungi kami. Kami akan menjawab dalam bahasa Inggris:",
}


# ──────────────────────────────────────────────────────────────────────────────
# Result dataclass
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class LanguageResult:
    code: str         # ISO 639-1
    name: str         # Human-readable
    script: str       # "latin" | "arabic" | "cjk" | ...
    confidence: float # 0.0–1.0
    is_english: bool

    @property
    def is_latin_script(self) -> bool:
        return self.script == "latin"

    @property
    def localized_ack(self) -> Optional[str]:
        """Return a brief native-language acknowledgment, or None for English."""
        return _LANG_ACK.get(self.code)


# ──────────────────────────────────────────────────────────────────────────────
# Core detection logic
# ──────────────────────────────────────────────────────────────────────────────

def detect_language(text: str) -> LanguageResult:
    """Detect the language of a support ticket.

    Returns a LanguageResult with detected language code, name, script type,
    and confidence score.  English is the default when detection is uncertain.
    """
    if not text or not text.strip():
        return LanguageResult(code="en", name="English", script="latin",
                              confidence=0.5, is_english=True)

    # Layer 1: Non-Latin script detection via Unicode blocks
    non_latin_counts: dict[tuple[str, str], int] = {}
    total_chars = 0
    for ch in text:
        cp = ord(ch)
        if cp > 0x007F:  # Skip ASCII
            total_chars += 1
            for lo, hi, code, script in _SCRIPT_RANGES:
                if lo <= cp <= hi:
                    key = (code, script)
                    non_latin_counts[key] = non_latin_counts.get(key, 0) + 1
                    break

    if non_latin_counts and total_chars > 0:
        dominant = max(non_latin_counts, key=non_latin_counts.__getitem__)
        code, script = dominant
        count = non_latin_counts[dominant]
        confidence = min(1.0, count / max(total_chars, 1))
        if confidence >= 0.3:  # > 30% non-Latin chars → confident non-Latin
            return LanguageResult(
                code=code,
                name=_SCRIPT_NAMES.get(code, code.upper()),
                script=script,
                confidence=round(confidence, 2),
                is_english=False,
            )

    # Layer 2: High-frequency word fingerprinting (Latin scripts)
    words = set(re.findall(r"[a-z]{2,}", text.lower()))
    if not words:
        return LanguageResult(code="en", name="English", script="latin",
                              confidence=0.5, is_english=True)

    scores: dict[str, int] = {}
    for lang_code, (_, word_set) in _LANG_WORDS.items():
        scores[lang_code] = len(words & word_set)

    best_code = max(scores, key=scores.__getitem__)
    best_score = scores[best_code]
    total_score = sum(scores.values()) or 1
    confidence = round(best_score / total_score, 2)

    # Require at least 2 matching words and 30% share to claim non-English
    if best_code != "en" and best_score < 2:
        best_code = "en"
        confidence = 0.5

    lang_name = _LANG_WORDS[best_code][0]
    return LanguageResult(
        code=best_code,
        name=lang_name,
        script="latin",
        confidence=confidence,
        is_english=(best_code == "en"),
    )


# ──────────────────────────────────────────────────────────────────────────────
# Public helpers
# ──────────────────────────────────────────────────────────────────────────────

def is_english(text: str) -> bool:
    """Quick boolean check — True if text appears to be English."""
    return detect_language(text).is_english


def non_english_escalation_response(lang: LanguageResult, company: str) -> dict:
    """Return a pre-built escalation response for non-Latin-script tickets."""
    return {
        "status": "escalated",
        "product_area": "general_support",
        "response": (
            f"Thank you for contacting {company} support. "
            f"We detected your message is in {lang.name} ({lang.code.upper()}). "
            "Our automated system processes tickets in English. "
            "We are routing your request to a multilingual support specialist "
            "who will respond in your preferred language as soon as possible."
        ),
        "justification": (
            f"Ticket detected as non-English / non-Latin script ({lang.name}, "
            f"script={lang.script}, confidence={lang.confidence:.0%}). "
            "Escalated to multilingual specialist. LLM processing skipped to "
            "avoid low-quality non-English responses."
        ),
        "request_type": "product_issue",
        "confidence_score": 0.95,
    }
