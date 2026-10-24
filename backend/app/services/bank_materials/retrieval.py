"""Internal bank fragment retrieval (lexical, no LLM, no public API).

Read-only: caller supplies Session and an explicit set of OCR run IDs.
"""

from __future__ import annotations

import re
import unicodedata
from calendar import monthrange
from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.bank_materials import (
    BankDocument,
    BankDocumentFile,
    BankFragment,
    BankFragmentRegion,
    BankOcrRun,
)
from app.services.bank_materials.eligibility import compute_fragment_eligibility
from app.services.bank_materials.fragment_revision import list_latest_fragments_for_run

RetrievalMode = Literal["candidates", "evidence"]

DEFAULT_LIMIT = 10
MAX_LIMIT = 50
MAX_QUERY_CHARS = 2000
# Evidence mode: require at least one exact token hit (3.0) or stronger combined
# signals. A single weak stem (2.0) — e.g. shared «спрос» — must not surface
# unrelated notes as AI evidence.
MIN_EVIDENCE_SCORE = 3.0

# Explicit small synonym groups (not embeddings). Documented in BANK_FRAGMENT_RETRIEVAL.md.
# Strong topical terms only — avoid ultra-generic tokens (банк/цб) as synonym bridges.
TOPIC_SYNONYMS: dict[str, frozenset[str]] = {
    "key_rate": frozenset(
        {
            "ставка",
            "ключевая",
            "ключевой",
            "ключевую",
            "пауза",
            "паузы",
            "сохранение",
            "сохранении",
            "сохранения",
            "неизменной",
            "неизменна",
            "риторика",
            "жестче",
            "жёстче",
        }
    ),
    "rate_forecast": frozenset(
        {
            "прогноз",
            "прогнозу",
            "прогноза",
            "ожидаем",
            "ожидает",
            "ожидание",
            "траектория",
            "2027",
            "октября",
        }
    ),
}

_STOPWORDS = frozenset(
    {
        "и",
        "в",
        "во",
        "на",
        "по",
        "о",
        "об",
        "от",
        "для",
        "что",
        "это",
        "как",
        "к",
        "с",
        "со",
        "а",
        "но",
        "же",
        "ли",
        "или",
        "то",
        "не",
        "из",
        "у",
        "за",
        "до",
        "при",
        "бы",
        "был",
        "была",
        "были",
        "быть",
        "есть",
        "the",
        "a",
        "an",
        "of",
        "to",
        "in",
        "on",
        "for",
        "is",
        "are",
        "and",
        "or",
        "банк",  # too common alone; not a synonym bridge
        "банка",
        "банку",
        "банком",
        "пишет",
        "какой",
        "какая",
        "какие",
        "про",
        "года",
        "году",
        "конец",
        "конца",
        # Generic calendar / magnitude tokens — alone they bridge unrelated notes.
        "месяц",
        "месяца",
        "месяце",
        "месяцы",
        "месяцев",
        "годовой",
        "годовая",
        "годовое",
        "годовом",
        "годовых",
        "процент",
        "процента",
        "процентов",
        "около",
        "уровень",
        "уровня",
        "уровне",
        # Demo / stage markers must not score as topical evidence.
        "синтетический",
        "синтетическая",
        "синтетические",
        "тест",
        # Ultra-generic connectors / verbs that bridge unrelated macro notes
        # (e.g. inflation query ↔ consumption «в годовом выражении», «вырос»;
        # «без копирования» ↔ «без изменения» in a rate quote).
        "без",
        "вырос",
        "выросла",
        "выросло",
        "выросли",
        "выражение",
        "выражения",
        "выражении",
        "выражением",
    }
)

_TOKEN_RE = re.compile(r"[0-9a-zа-яё]+", re.IGNORECASE)


class RetrievalError(ValueError):
    def __init__(self, code: str, detail: str):
        self.code = code
        self.detail = detail
        super().__init__(f"[{code}] {detail}")


@dataclass(frozen=True)
class RegionHit:
    page_number: int
    sort_order: int
    region_type: str
    bbox_left: int | None
    bbox_top: int | None
    bbox_width: int | None
    bbox_height: int | None
    note: str | None


@dataclass(frozen=True)
class FragmentHit:
    document_id: str
    document_file_id: str
    ocr_run_id: str
    fragment_id: str
    stable_key: str
    revision: int
    document_slug: str
    document_title: str | None
    publication_date: date | None
    publication_year: int | None
    publication_month: int | None
    publication_date_precision: str
    publication_date_display: str | None
    staleness_note: str | None
    is_current_stance: bool
    page_number: int
    regions: tuple[RegionHit, ...]
    content_type: str | None
    content_type_status: str
    text_kind: str  # exact_quote | summary | untrusted_candidate
    text: str
    kind: str  # fragment kind
    verification_status: str
    primary_region_type: str
    eligible_search: bool
    eligible_ai_evidence: bool
    eligible_exact_quote: bool
    eligibility_reasons: tuple[str, ...]
    pdf_sha256: str
    ocr_fingerprint_hash: str
    source_role: str | None
    source_role_meaning: str
    qa_method: str | None
    qa_performed_by: str | None
    qa_performed_at: str | None
    relevance_score: float
    match_reasons: tuple[str, ...]
    date_gate_reasons: tuple[str, ...]
    insufficient_verification: bool


@dataclass
class RetrievalResult:
    mode: str
    query: str
    query_normalized_tokens: tuple[str, ...]
    as_of_date: date | None
    ocr_run_ids: tuple[str, ...]
    limit: int
    hits: list[FragmentHit] = field(default_factory=list)
    empty_reason: str | None = None
    algorithm_notes: tuple[str, ...] = field(default_factory=tuple)

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "query": self.query,
            "query_normalized_tokens": list(self.query_normalized_tokens),
            "as_of_date": self.as_of_date.isoformat() if self.as_of_date else None,
            "ocr_run_ids": list(self.ocr_run_ids),
            "limit": self.limit,
            "empty_reason": self.empty_reason,
            "algorithm_notes": list(self.algorithm_notes),
            "hit_count": len(self.hits),
            "hits": [asdict(h) for h in self.hits],
        }


def normalize_query_text(text: str) -> str:
    """Lowercase, ё→е, strip combining marks lightly, keep letters/digits/spaces."""
    s = unicodedata.normalize("NFKC", text or "")
    s = s.replace("Ё", "е").replace("ё", "е")
    s = s.casefold()
    s = re.sub(r"[^\w\s0-9a-zа-я]+", " ", s, flags=re.UNICODE)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def tokenize(text: str) -> list[str]:
    norm = normalize_query_text(text)
    return [t for t in _TOKEN_RE.findall(norm) if t]


def query_tokens(text: str) -> list[str]:
    """Tokenize query; drop stopwords; dedupe preserving order.

    Deduping prevents a repeated weak stem (e.g. «спрос» in title+summary)
    from stacking past the evidence score floor without new topical signal.
    """
    out: list[str] = []
    seen: set[str] = set()
    for t in tokenize(text):
        if t in _STOPWORDS or len(t) <= 1:
            continue
        if t in seen:
            continue
        seen.add(t)
        out.append(t)
    return out


def _stemish(token: str) -> str:
    """Very light suffix trim for RU morphology (deterministic, not a full stemmer)."""
    t = token
    for suf in (
        "ями",
        "ами",
        "ов",
        "ев",
        "ей",
        "ой",
        "ий",
        "ый",
        "ая",
        "ое",
        "ые",
        "ие",
        "ию",
        "ью",
        "ях",
        "ах",
        "ом",
        "ем",
        "у",
        "ю",
        "а",
        "я",
        "ы",
        "и",
        "е",
    ):
        if len(t) > len(suf) + 3 and t.endswith(suf):
            return t[: -len(suf)]
    return t


def _token_in_group(token: str, group: frozenset[str]) -> bool:
    if token in group:
        return True
    stem = _stemish(token)
    for g in group:
        if token == g or stem == _stemish(g):
            return True
        if len(g) >= 4 and (token.startswith(g) or g.startswith(token)):
            return True
    return False


def synonym_group_for(token: str) -> frozenset[str] | None:
    for group in TOPIC_SYNONYMS.values():
        if _token_in_group(token, group):
            return group
    return None


def score_fragment_text(
    *,
    query_toks: list[str],
    fragment_text: str,
    document_title: str | None,
    stable_key: str,
    content_type: str | None,
) -> tuple[float, list[str]]:
    """Deterministic lexical score + match reasons. Not confidence."""
    reasons: list[str] = []
    if not query_toks:
        return 0.0, ["empty_query_tokens"]

    frag_toks = tokenize(fragment_text)
    frag_set = set(frag_toks)
    frag_stems = {_stemish(t) for t in frag_toks}
    title_toks = set(tokenize(document_title or ""))
    title_stems = {_stemish(t) for t in title_toks}
    key_toks = set(tokenize(stable_key.replace("_", " ")))

    score = 0.0
    matched_exact: list[str] = []
    matched_stem: list[str] = []
    matched_syn: list[str] = []

    for qt in query_toks:
        qs = _stemish(qt)
        if qt in frag_set:
            score += 3.0
            matched_exact.append(qt)
        elif qs in frag_stems:
            score += 2.0
            matched_stem.append(qt)
        else:
            group = synonym_group_for(qt)
            if group is None:
                continue
            # Synonym hit only when another group member appears in fragment text.
            for g in group:
                if g == qt:
                    continue
                if g in frag_set or _stemish(g) in frag_stems:
                    score += 1.5
                    matched_syn.append(f"{qt}~{g}")
                    break

    for name, group in TOPIC_SYNONYMS.items():
        q_hit = any(_token_in_group(qt, group) for qt in query_toks)
        f_hits = sum(1 for g in group if g in frag_set or _stemish(g) in frag_stems)
        if q_hit and f_hits >= 2:
            score += 1.0 + 0.25 * min(f_hits, 4)
            reasons.append(f"topic_overlap:{name}:{f_hits}")

    if matched_exact:
        reasons.append("token_exact:" + ",".join(sorted(set(matched_exact))[:8]))
    if matched_stem:
        reasons.append("token_stem:" + ",".join(sorted(set(matched_stem))[:8]))
    if matched_syn:
        reasons.append("token_syn:" + ",".join(sorted(set(matched_syn))[:8]))

    # Title-only match must NOT auto-qualify all fragments: small additive, needs fragment signal
    title_overlap = sum(
        1 for qt in query_toks if qt in title_toks or _stemish(qt) in title_stems
    )
    if title_overlap and score > 0:
        score += 0.3 * title_overlap
        reasons.append(f"title_support:{title_overlap}")
    elif title_overlap and score == 0:
        reasons.append("title_only_insufficient")

    # stable_key tokens — weak support only with fragment text hits
    key_overlap = sum(1 for qt in query_toks if qt in key_toks or _stemish(qt) in key_toks)
    if key_overlap and score > 0:
        score += 0.2 * key_overlap
        reasons.append(f"stable_key_support:{key_overlap}")

    # Type boosts only after a real fragment-text signal (never query-only).
    if score > 0:
        if content_type == "forecast" and any(
            t.startswith("прогноз") or t.startswith("ожида") or t == "2027"
            for t in query_toks
        ):
            score += 0.5
            reasons.append("content_type_forecast_boost")
        if content_type == "fact" and any(
            t.startswith("решен") or t.startswith("сохран") or "ставк" in t
            for t in query_toks
        ):
            score += 0.4
            reasons.append("content_type_fact_boost")

    return score, reasons


def publication_passes_as_of(
    *,
    precision: str,
    publication_date: date | None,
    publication_year: int | None,
    publication_month: int | None,
    as_of: date | None,
    mode: RetrievalMode,
) -> tuple[bool, list[str]]:
    """Temporal gate. Evidence is strict; candidates may surface uncertain dates with reasons."""
    reasons: list[str] = []
    if as_of is None:
        return True, ["as_of_not_set"]

    if precision == "day":
        if publication_date is None:
            reasons.append("day_precision_missing_date")
            return (mode == "candidates"), reasons
        if publication_date > as_of:
            reasons.append(f"published_after_as_of:{publication_date.isoformat()}")
            return False, reasons
        reasons.append("day_on_or_before_as_of")
        return True, reasons

    if precision == "month":
        if publication_year is None or publication_month is None:
            reasons.append("month_precision_incomplete")
            return (mode == "candidates"), reasons
        # Earliest possible day in month
        first = date(publication_year, publication_month, 1)
        last_day = monthrange(publication_year, publication_month)[1]
        last = date(publication_year, publication_month, last_day)
        if first > as_of:
            # Entire month is after as_of
            reasons.append(
                f"month_starts_after_as_of:{publication_year}-{publication_month:02d}"
            )
            return False, reasons
        if last > as_of:
            # Month overlaps as_of: cannot assert published by as_of
            reasons.append(
                f"month_day_unknown_overlaps_as_of:{publication_year}-{publication_month:02d}"
            )
            if mode == "evidence":
                return False, reasons
            return True, reasons
        # Entire month ends on/before as_of
        reasons.append("month_fully_on_or_before_as_of")
        return True, reasons

    # unknown
    reasons.append("publication_date_unknown")
    if mode == "evidence":
        return False, reasons
    return True, reasons


def source_role_meaning(source_role: str | None, *, content_type: str | None) -> str:
    """Explain stored source_role without inventing a different stored value."""
    if source_role == "bank_material_qa_revision":
        return (
            "Fragment revision produced via QA on a bank research PDF; "
            "source remains the bank material (not a direct CB feed). "
            "QA method is separate from source role."
        )
    if source_role:
        return f"Stored source_role={source_role!r} (unchanged)."
    if content_type == "fact":
        return (
            "No explicit source_role; text is from bank materials corpus "
            "(bank-reported claims, not a live CB API)."
        )
    return "No explicit source_role; text is from bank materials corpus."


def _display_text_and_kind(
    frag: BankFragment,
    *,
    mode: RetrievalMode,
    elig_quote: bool,
    elig_ai: bool,
) -> tuple[str, str, bool]:
    """Return (text, text_kind, insufficient_verification)."""
    if mode == "evidence":
        if frag.kind == "exact_quote" and elig_quote and frag.verified_transcript:
            return frag.verified_transcript, "exact_quote", False
        if frag.kind == "summary" and elig_ai and frag.summary_text:
            return frag.summary_text, "summary", False
        # Should not reach if eligibility filtered correctly
        return (frag.summary_text or frag.verified_transcript or ""), "summary", True

    # candidates
    insufficient = not elig_ai
    if frag.kind == "exact_quote" and frag.verified_transcript:
        kind = "exact_quote" if elig_quote else "untrusted_candidate"
        return frag.verified_transcript, kind, insufficient
    if frag.kind == "summary" and frag.summary_text:
        kind = "summary" if elig_ai else "untrusted_candidate"
        return frag.summary_text, kind, insufficient
    # fallback to ocr_text for navigation only
    return (frag.ocr_text or ""), "untrusted_candidate", True


def retrieve_bank_fragments(
    session: Session,
    *,
    query: str,
    ocr_run_ids: list[str] | tuple[str, ...],
    mode: RetrievalMode = "candidates",
    limit: int = DEFAULT_LIMIT,
    as_of_date: date | None = None,
) -> RetrievalResult:
    """Search latest revisions inside the given OCR runs only (read-only)."""
    if mode not in ("candidates", "evidence"):
        raise RetrievalError("mode_invalid", f"mode must be candidates|evidence, got {mode!r}")
    if not ocr_run_ids:
        raise RetrievalError(
            "ocr_run_ids_required",
            "explicit ocr_run_ids required; refusing to search the whole corpus by default",
        )
    run_ids = tuple(dict.fromkeys(str(x) for x in ocr_run_ids))  # stable unique order
    if limit < 1:
        raise RetrievalError("limit_invalid", "limit must be >= 1")
    limit_i = min(int(limit), MAX_LIMIT)

    q = (query or "").strip()
    if len(q) > MAX_QUERY_CHARS:
        raise RetrievalError(
            "query_too_long",
            f"query exceeds {MAX_QUERY_CHARS} characters",
        )
    q_toks = query_tokens(q)
    notes = (
        "deterministic_lexical_retrieval",
        "no_embeddings",
        "no_llm",
        "latest_revision_only_per_stable_key",
        "no_fallback_to_older_revision",
        "title_only_match_insufficient",
        "relevance_score_is_not_confidence",
        f"evidence_requires_score_ge_{MIN_EVIDENCE_SCORE:g}",
        "explicit_topic_synonym_groups:" + ",".join(sorted(TOPIC_SYNONYMS)),
    )

    # Validate runs exist
    existing_runs = {
        r.id: r
        for r in session.scalars(select(BankOcrRun).where(BankOcrRun.id.in_(run_ids))).all()
    }
    missing = [rid for rid in run_ids if rid not in existing_runs]
    if missing:
        raise RetrievalError(
            "ocr_run_not_found",
            f"unknown ocr_run_ids: {missing[:5]}",
        )

    files = {
        f.id: f
        for f in session.scalars(
            select(BankDocumentFile).where(
                BankDocumentFile.id.in_({r.document_file_id for r in existing_runs.values()})
            )
        ).all()
    }
    docs = {
        d.id: d
        for d in session.scalars(
            select(BankDocument).where(
                BankDocument.id.in_({f.document_id for f in files.values()})
            )
        ).all()
    }

    scored: list[tuple[float, str, str, FragmentHit]] = []
    # sort key uses (-score, stable_key, fragment_id) for stability

    for run_id in run_ids:
        run = existing_runs[run_id]
        file = files[run.document_file_id]
        doc = docs[file.document_id]
        latest = list_latest_fragments_for_run(session, ocr_run_id=run_id)
        for sel in latest:
            frag = sel.fragment
            elig = sel.eligibility
            if mode == "candidates" and not elig.eligible_search:
                continue
            if mode == "evidence" and not elig.eligible_ai_evidence:
                continue

            ok_date, date_reasons = publication_passes_as_of(
                precision=doc.publication_date_precision,
                publication_date=doc.publication_date,
                publication_year=doc.publication_year,
                publication_month=doc.publication_month,
                as_of=as_of_date,
                mode=mode,
            )
            if not ok_date:
                continue

            # Text used for matching: prefer transcript/summary, never invent
            match_text = " ".join(
                x
                for x in (
                    frag.verified_transcript,
                    frag.summary_text,
                    frag.ocr_text,
                    frag.stable_key.replace("_", " "),
                )
                if x
            )
            # Do not use document title as primary match corpus for this fragment
            score, match_reasons = score_fragment_text(
                query_toks=q_toks,
                fragment_text=match_text,
                document_title=doc.title,
                stable_key=frag.stable_key,
                content_type=frag.content_type,
            )
            if score <= 0:
                continue
            if mode == "evidence" and score < MIN_EVIDENCE_SCORE:
                continue

            text, text_kind, insufficient = _display_text_and_kind(
                frag,
                mode=mode,
                elig_quote=elig.eligible_exact_quote,
                elig_ai=elig.eligible_ai_evidence,
            )
            if mode == "evidence" and text_kind == "untrusted_candidate":
                continue
            if mode == "evidence" and not text.strip():
                continue

            regs = session.scalars(
                select(BankFragmentRegion)
                .where(BankFragmentRegion.fragment_id == frag.id)
                .order_by(BankFragmentRegion.sort_order)
            ).all()
            region_hits = tuple(
                RegionHit(
                    page_number=r.page_number,
                    sort_order=r.sort_order,
                    region_type=r.region_type,
                    bbox_left=r.bbox_left,
                    bbox_top=r.bbox_top,
                    bbox_width=r.bbox_width,
                    bbox_height=r.bbox_height,
                    note=r.note,
                )
                for r in regs
            )

            corr = frag.ocr_correction_json if isinstance(frag.ocr_correction_json, dict) else {}
            prov = corr.get("qa_provenance") if isinstance(corr.get("qa_provenance"), dict) else {}

            hit = FragmentHit(
                document_id=doc.id,
                document_file_id=file.id,
                ocr_run_id=run.id,
                fragment_id=frag.id,
                stable_key=frag.stable_key,
                revision=frag.revision,
                document_slug=doc.slug,
                document_title=doc.title,
                publication_date=doc.publication_date,
                publication_year=doc.publication_year,
                publication_month=doc.publication_month,
                publication_date_precision=doc.publication_date_precision,
                publication_date_display=doc.publication_date_display,
                staleness_note=doc.staleness_note,
                is_current_stance=bool(doc.is_current_stance),
                page_number=frag.page_number,
                regions=region_hits,
                content_type=frag.content_type,
                content_type_status=frag.content_type_status,
                text_kind=text_kind,
                text=text,
                kind=frag.kind,
                verification_status=frag.verification_status,
                primary_region_type=frag.primary_region_type,
                eligible_search=elig.eligible_search,
                eligible_ai_evidence=elig.eligible_ai_evidence,
                eligible_exact_quote=elig.eligible_exact_quote,
                eligibility_reasons=tuple(elig.reasons),
                pdf_sha256=file.sha256,
                ocr_fingerprint_hash=run.fingerprint_hash,
                source_role=frag.source_role,
                source_role_meaning=source_role_meaning(
                    frag.source_role, content_type=frag.content_type
                ),
                qa_method=str(prov["method"]) if prov.get("method") else None,
                qa_performed_by=str(prov["performed_by"]) if prov.get("performed_by") else None,
                qa_performed_at=str(prov["performed_at"]) if prov.get("performed_at") else None,
                relevance_score=round(score, 4),
                match_reasons=tuple(match_reasons),
                date_gate_reasons=tuple(date_reasons),
                insufficient_verification=insufficient,
            )
            scored.append((-score, frag.stable_key, frag.id, hit))

    scored.sort(key=lambda x: (x[0], x[1], x[2]))
    hits = [h for _, _, _, h in scored[:limit_i]]

    empty_reason = None
    if not hits:
        if not q_toks:
            empty_reason = "no_indexable_query_tokens"
        else:
            empty_reason = "no_matching_fragments_in_scope"

    return RetrievalResult(
        mode=mode,
        query=q,
        query_normalized_tokens=tuple(q_toks),
        as_of_date=as_of_date,
        ocr_run_ids=run_ids,
        limit=limit_i,
        hits=hits,
        empty_reason=empty_reason,
        algorithm_notes=notes,
    )
