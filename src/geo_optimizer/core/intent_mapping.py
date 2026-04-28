"""AI Search Intent Mapping (#385).

Analizza il contenuto di una pagina per determinare quali intenti di ricerca AI
serve e quanto e' pronta a essere citata per ciascuno.

Zero fetch HTTP — lavora su dati gia disponibili.
Basato su: Princeton KDD 2024, AutoGEO ICLR 2026, Google Search Intent taxonomy.
"""

from __future__ import annotations

import re
from typing import Any

from geo_optimizer.models.results import ContentResult, IntentMappingResult, MetaResult, SchemaResult

# ─── Pattern di intenti ──────────────────────────────────────────────────────

_INTENT_PATTERNS: dict[str, dict[str, Any]] = {
    "informational": {
        "patterns": [
            r"\b(what is|what are|how to|how do|how does|why is|why does|"
            r"tutorial|guide|explained|definition|meaning|overview|basics|"
            r"cosa e|cosa sono|come fare|come si|perche|guida|spiegazione|"
            r"introduzione|principianti|fondamenti)\b",
        ],
        "schema_required": {"FAQPage", "HowTo", "TechArticle", "Article"},
        "weight": 1.0,
    },
    "navigational": {
        "patterns": [
            r"\b(login|sign in|register|sign up|home|homepage|portal|"
            r"dashboard|account|profile|contact us|about us|terms|privacy|"
            r"accedi|registrati|home|portale|dashboard|profilo|contatti|"
            r"chi siamo|termini|privacy)\b",
        ],
        "schema_required": {"WebSite", "Organization", "BreadcrumbList"},
        "weight": 0.8,
    },
    "transactional": {
        "patterns": [
            r"\b(buy|purchase|order|subscribe|download|free trial|demo|"
            r"get started|sign up now|pricing|quote|checkout|cart|"
            r"acquista|ordina|abbonati|scarica|prova gratis|"
            r"inizia ora|prezzi|preventivo|carrello)\b",
        ],
        "schema_required": {"Product", "Offer", "WebApplication", "LocalBusiness"},
        "weight": 1.0,
    },
    "commercial": {
        "patterns": [
            r"\b(best|top|vs|versus|compare|comparison|review|reviews|"
            r"alternatives|features|pros and cons| which is better|"
            r"miglior|migliore|top|confronto|paragone|recensione|"
            r"alternative|caratteristiche|pro e contro)\b",
        ],
        "schema_required": {"Product", "Article", "FAQPage", "HowTo"},
        "weight": 1.2,
    },
}

# Sezioni della pagina: ordine per priorita estrazione
_CONTENT_SECTIONS = ["h1", "title", "h2", "h3", "h4", "h5", "h6", "meta_description"]


def _extract_page_text(soup, content: ContentResult, meta: MetaResult) -> str:
    """Estrae testo rilevante per analisi intenti (heading, title, meta)."""
    parts: list[str] = []

    # H1 e heading hierarchy — priorita piu alta
    if content.has_h1 and content.h1_text:
        parts.append(content.h1_text)

    # Meta title
    if meta.title_text:
        parts.append(meta.title_text)

    # H2-H6 dal soup se disponibile
    if soup is not None:
        for level in range(2, 7):
            for tag in soup.find_all(f"h{level}"):
                text = tag.get_text(strip=True)
                if text:
                    parts.append(text)

        # Meta description
        desc_tag = soup.find("meta", attrs={"name": "description"})
        if desc_tag and desc_tag.get("content"):
            parts.append(desc_tag["content"])

    # Testo principale dalla pagina
    if soup is not None:
        main = soup.find("main") or soup.find("article") or soup.body
        if main:
            text = main.get_text(separator=" ", strip=True)
            if text:
                # Solo le prime 2000 parole per performance
                words = text.split()[:2000]
                parts.append(" ".join(words))

    return " ".join(parts).lower()


def _score_text_for_intents(text: str) -> dict[str, list[str]]:
    """Trova tutti i match per ogni categoria di intento.

    Returns:
        dict {category: [matched_phrase, ...]}
    """
    results: dict[str, list[str]] = {cat: [] for cat in _INTENT_PATTERNS}

    for category, cfg in _INTENT_PATTERNS.items():
        for pattern in cfg["patterns"]:
            found = re.findall(pattern, text, re.IGNORECASE)
            results[category].extend(f for f in found if isinstance(f, str))

    return results


def _check_schema_for_intent(category: str, schema_result: SchemaResult) -> tuple[bool, list[str]]:
    """Verifica se esiste almeno uno schema richiesto per la categoria.

    Returns:
        (found: bool, matched_schemas: list)
    """
    required = _INTENT_PATTERNS[category]["schema_required"]
    matched: list[str] = []

    for raw in schema_result.raw_schemas:
        if not isinstance(raw, dict):
            continue
        schemas = []
        if "@graph" in raw:
            schemas.extend(raw["@graph"])
        else:
            schemas.append(raw)

        for s in schemas:
            s_type = s.get("@type", "")
            if isinstance(s_type, list):
                s_type = s_type[0] if s_type else ""
            if s_type and s_type in required:
                matched.append(s_type)

    return bool(matched), list(set(matched))


def _estimate_intent_coverage(category: str, signals: list[str], schema_ok: bool) -> dict[str, Any]:
    """Stima la copertura di un intento basandosi su segnali e schema.

    Returns:
        dict con coverage_score (0-100), signals_found, schema_matched.
    """
    unique_signals = list(set(signals))
    signal_count = len(unique_signals)
    weight = _INTENT_PATTERNS[category]["weight"]

    # Base score: segnali unici trovati (max 60 punti)
    signal_score = min(signal_count * 20, 60)

    # Boost schema: +30 punti se presente schema appropriato
    schema_score = 30 if schema_ok else 0

    # Penalty per mancanza di supporto schema (-10 se nessuno)
    schema_penalty = -10 if not schema_ok else 0

    raw = signal_score + schema_score + schema_penalty
    coverage = max(0, min(100, int(raw * weight)))

    return {
        "coverage_score": coverage,
        "signals_found": unique_signals[:5],  # max 5 per non gonfiare json
        "signals_count": signal_count,
        "schema_matched": schema_ok,
        "has_relevant_schema": schema_ok,
    }


def audit_intent_mapping(
    soup,
    raw_html: str,  # noqa: ARG001  reserved for future extensions
    content_result: ContentResult,
    meta_result: MetaResult,
    schema_result: SchemaResult,
) -> IntentMappingResult:
    """Mappa gli intenti di ricerca AI serviti dalla pagina.

    Args:
        soup: BeautifulSoup della pagina.
        raw_html: HTML grezzo (riservato per estensioni future).
        content_result: ContentResult gia calcolato.
        meta_result: MetaResult gia calcolato.
        schema_result: SchemaResult gia calcolato.

    Returns:
        IntentMappingResult con intenti trovati, mancanti e punteggio.
    """
    result = IntentMappingResult()
    if soup is None:
        return result

    result.checked = True

    # Estrazione testo
    text = _extract_page_text(soup, content_result, meta_result)

    # Pattern matching
    intent_signals = _score_text_for_intents(text)

    # Analisi per categoria
    category_scores: dict[str, int] = {}
    for category in _INTENT_PATTERNS:
        signals = intent_signals[category]
        schema_ok, schema_types = _check_schema_for_intent(category, schema_result)

        # Se non ci sono segnali e non c'e schema: intento mancante
        if not signals and not schema_ok:
            result.intents_missing.append(category)
            category_scores[category] = 0
            continue

        # Se ci sono segnali o schema: intento presente, valutiamo coverage
        result.intents_found.append(category)
        estimation = _estimate_intent_coverage(category, signals, schema_ok)
        result.intent_details[category] = estimation
        category_scores[category] = estimation["coverage_score"]

    # Calcolo score composito (media dei coverage, 0-100)
    if category_scores:
        result.score = round(sum(category_scores.values()) / len(category_scores))

    # Calcolo readiness
    ready = sum(1 for cat, data in result.intent_details.items() if data.get("schema_matched"))
    total_found = len(result.intents_found)
    result.ai_ready_count = ready
    result.ai_unready_count = total_found - ready
    result.total_intents_found = total_found
    result.total_intents_missing = len(result.intents_missing)

    # Banding
    if result.score >= 70:
        result.band = "good"
    elif result.score >= 40:
        result.band = "foundation"
    else:
        result.band = "critical"

    return result
