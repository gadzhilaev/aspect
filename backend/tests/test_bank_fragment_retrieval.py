"""Bank fragment retrieval: synthetic SQLite, read-only."""

from __future__ import annotations

import os
import tempfile
import uuid
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.models.bank_materials import BankFragment, BankFragmentRegion
from app.services.bank_materials.apply_qa_revisions import (
    apply_qa_revisions,
    load_qa_artifact,
)
from app.services.bank_materials.load import load_bank_document
from app.services.bank_materials.prepare import build_prepared_document, stage_corpus
from app.services.bank_materials.retrieval import (
    RetrievalError,
    publication_passes_as_of,
    retrieve_bank_fragments,
)
from tests.test_bank_import_dry_run import _build_valid_corpus, _confirmed_fragment
from tests.test_bank_qa_revisions import _qa_artifact, _seed_doc

ROOT = Path(__file__).resolve().parents[1]


def _alembic_config() -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "alembic"))
    return cfg


@contextmanager
def _with_db_url(db_url: str):
    prev = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = db_url
    get_settings.cache_clear()
    try:
        yield
    finally:
        if prev is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = prev
        get_settings.cache_clear()


def _sqlite_migrated():
    tmp = tempfile.TemporaryDirectory()
    path = Path(tmp.name) / "ret.db"
    url = f"sqlite:///{path.as_posix()}"
    engine = create_engine(url)

    @event.listens_for(engine, "connect")
    def _fk(dbapi_conn, _connection_record):  # noqa: ANN001
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    with _with_db_url(url):
        command.upgrade(_alembic_config(), "head")
    return tmp, engine, url


def _session(engine):
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)()


def _prepare_with_qa(tmp_path: Path, engine):
    staging, plan = _seed_doc(tmp_path, engine, slug="ret-doc")
    art = _qa_artifact(plan, out=tmp_path / "qa.json")
    data, sha = load_qa_artifact(art)
    with _session(engine) as session:
        apply_qa_revisions(session, data, artifact_sha256=sha)
        session.commit()
        run_id = session.scalars(select(BankFragment)).first().ocr_run_id
    return plan, run_id


def test_publication_date_gates():
    as_of = date(2026, 9, 11)
    ok, _ = publication_passes_as_of(
        precision="day",
        publication_date=date(2026, 9, 11),
        publication_year=2026,
        publication_month=9,
        as_of=as_of,
        mode="evidence",
    )
    assert ok
    ok, reasons = publication_passes_as_of(
        precision="day",
        publication_date=date(2026, 9, 12),
        publication_year=2026,
        publication_month=9,
        as_of=as_of,
        mode="evidence",
    )
    assert not ok
    assert any("published_after" in r for r in reasons)

    ok_e, reasons_e = publication_passes_as_of(
        precision="month",
        publication_date=None,
        publication_year=2026,
        publication_month=9,
        as_of=as_of,
        mode="evidence",
    )
    assert not ok_e
    ok_c, reasons_c = publication_passes_as_of(
        precision="month",
        publication_date=None,
        publication_year=2026,
        publication_month=9,
        as_of=as_of,
        mode="candidates",
    )
    assert ok_c
    assert any("overlaps" in r for r in reasons_c)

    ok_u, _ = publication_passes_as_of(
        precision="unknown",
        publication_date=None,
        publication_year=None,
        publication_month=None,
        as_of=as_of,
        mode="evidence",
    )
    assert not ok_u


def test_relevant_vs_irrelevant_and_modes(tmp_path: Path):
    tmp, engine, url = _sqlite_migrated()
    try:
        plan, run_id = _prepare_with_qa(tmp_path, engine)
        with _session(engine) as session:
            before = session.scalar(select(func.count()).select_from(BankFragment))
            cand = retrieve_bank_fragments(
                session,
                query="decision verified contiguous forecast",
                ocr_run_ids=[run_id],
                mode="candidates",
                limit=10,
            )
            ev = retrieve_bank_fragments(
                session,
                query="decision verified contiguous forecast",
                ocr_run_ids=[run_id],
                mode="evidence",
                limit=10,
            )
            odd = retrieve_bank_fragments(
                session,
                query="цены на алюминий на лондонской бирже",
                ocr_run_ids=[run_id],
                mode="evidence",
                limit=10,
            )
            after = session.scalar(select(func.count()).select_from(BankFragment))
        assert before == after  # read-only
        assert cand.hits
        # evidence: only AI-eligible (rev2)
        assert ev.hits
        assert all(h.eligible_ai_evidence for h in ev.hits)
        assert all(h.text_kind in ("exact_quote", "summary") for h in ev.hits)
        assert all(not h.insufficient_verification for h in ev.hits)
        assert odd.hits == []
        assert odd.empty_reason
    finally:
        engine.dispose()
        tmp.cleanup()


def test_evidence_rejects_single_weak_stem_false_positive(tmp_path: Path):
    """A lone shared stem (score 2.0) must not become AI evidence.

    Real corpus case: gold «спрос» vs consumption «спроса» — not topical overlap.
    Repeated «спрос» in title+summary must not stack past the evidence floor.
    """
    from app.services.bank_materials.retrieval import (
        MIN_EVIDENCE_SCORE,
        query_tokens,
        score_fragment_text,
    )

    assert MIN_EVIDENCE_SCORE == 3.0
    # Same tokenization path as retrieve_bank_fragments (stopwords dropped + dedupe).
    q_toks = query_tokens(
        "ювелирный спрос на золото на мировом рынке растёт ювелирный спрос на золото"
    )
    assert q_toks.count("спрос") == 1
    score, reasons = score_fragment_text(
        query_toks=q_toks,
        fragment_text=(
            "Мы полагаем, что динамика потребления сейчас находится на пике "
            "и в следующие месяцы будет происходить постепенное охлаждение "
            "темпов роста спроса — в 4К26 ориентир около нуля."
        ),
        document_title="Потребление на пике",
        stable_key="consumption_peak_forecast",
        content_type="forecast",
    )
    assert score < MIN_EVIDENCE_SCORE, (score, reasons, q_toks)
    assert any(r.startswith("token_stem:") for r in reasons)
    assert not any(r.startswith("token_exact:") for r in reasons)

    tmp, engine, url = _sqlite_migrated()
    try:
        _, run_id = _prepare_with_qa(tmp_path, engine)
        with _session(engine) as session:
            ev = retrieve_bank_fragments(
                session,
                query="ювелирный спрос на золото",
                ocr_run_ids=[run_id],
                mode="evidence",
                limit=10,
            )
            # Policy Rate corpus has no gold topic — evidence must stay empty
            assert ev.hits == []
    finally:
        engine.dispose()
        tmp.cleanup()


def test_evidence_rejects_generic_exact_bridges_across_macro_themes():
    """One exact hit on a generic connector must not qualify cross-theme evidence.

    Inflation wording shares «выражении» / «вырос» / «без» with consumption and
    rate quotes; those tokens are stopwords so topical stems still decide.
    Paraphrases used here were not the stage-6.8 matrix strings used to find
    the defect.
    """
    from app.services.bank_materials.retrieval import (
        MIN_EVIDENCE_SCORE,
        query_tokens,
        score_fragment_text,
    )

    # Exact lemma «инфляция» (as match_categories often inject) — stem alone
    # is intentionally below the evidence floor.
    infl_q = query_tokens(
        "Недельный ИПЦ: дефляция по потребительским ценам, "
        "годовой уровень инфляция около шести процентов"
    )
    # Extra paraphrase not used when discovering the stopword set.
    infl_q_b = query_tokens(
        "Росстат отметил небольшое снижение цен за августовскую неделю; "
        "годовой показатель инфляция чуть выше шести процентов"
    )
    consumption_peak = (
        "Мы полагаем, что динамика потребления сейчас находится на пике "
        "и в следующие месяцы будет происходить постепенное охлаждение "
        "темпов роста спроса — в 4К26 мы ориентируемся на рост потребления "
        "на нулевых отметках в годовом выражении."
    )
    consumption_retail = "Оборот розничной торговли вырос на 7,3% г/г в июне"
    rate_rhetoric = "Ставка без изменения на 14,0%, риторика стала жестче"
    infl_fact = "В годовом выражении инфляция выросла до 6,32%."

    for q_toks in (infl_q, infl_q_b):
        for text, title, key, ctype in (
            (consumption_peak, "Потребление", "consumption_peak_forecast", "forecast"),
            (consumption_retail, "Потребление", "consumption_retail_june", "fact"),
            (rate_rhetoric, "Ставка", "policy_rate_rhetoric", "interpretation"),
        ):
            score, reasons = score_fragment_text(
                query_toks=q_toks,
                fragment_text=text,
                document_title=title,
                stable_key=key,
                content_type=ctype,
            )
            assert score < MIN_EVIDENCE_SCORE, (key, score, reasons, q_toks)

        infl_score, infl_reasons = score_fragment_text(
            query_toks=q_toks,
            fragment_text=infl_fact,
            document_title="Инфляция",
            stable_key="infl_yoy",
            content_type="fact",
        )
        assert infl_score >= MIN_EVIDENCE_SCORE, (infl_score, infl_reasons, q_toks)

    # Consumption query must still clear the floor on retail fact without «вырос».
    con_q = query_tokens(
        "Розничный оборот в июне остаётся высоким; потребительский спрос у пика"
    )
    con_score, con_reasons = score_fragment_text(
        query_toks=con_q,
        fragment_text=consumption_retail,
        document_title="Потребление",
        stable_key="consumption_retail_june",
        content_type="fact",
    )
    assert con_score >= MIN_EVIDENCE_SCORE, (con_score, con_reasons, con_q)


def test_event_query_strips_synthetic_brackets_and_steel_avoids_rate():
    """Demo bracket tags and metallurgy wording must not pull rate evidence."""
    from datetime import datetime, timezone

    from app.models import Event
    from app.services.bank_materials.event_evidence import build_event_search_query
    from app.services.bank_materials.retrieval import query_tokens, score_fragment_text

    ev = Event(
        id="evt_tmp_steel",
        title="[СИНТЕТИЧЕСКИЙ ТЕСТ 6.8] Цены на стальной прокат",
        summary="Котировки горячекатаного проката и загрузка меткомбинатов.",
        category="macro",
        event_type="risk",
        severity=1.0,
        urgency_default="watch",
        status="active",
        occurred_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
        match_countries_json=[],
        match_categories_json=["сталь"],
        match_currencies_json=[],
        match_materials_json=[],
        attributes_json={},
        is_demo=True,
    )
    q = build_event_search_query(ev)
    assert "синтетическ" not in q.casefold()
    toks = query_tokens(q)
    assert "синтетический" not in toks
    score, _ = score_fragment_text(
        query_toks=toks,
        fragment_text="ЦБ РФ принял решение оставить ставку неизменной на уровне 14,0%:",
        document_title="Ключевая ставка ЦБ РФ",
        stable_key="policy_rate_cb_decision",
        content_type="fact",
    )
    assert score < 3.0, score


def test_no_fallback_and_no_duplicate_revisions(tmp_path: Path):
    tmp, engine, url = _sqlite_migrated()
    try:
        _, run_id = _prepare_with_qa(tmp_path, engine)
        with _session(engine) as session:
            # Force latest of decision to unverified while keeping AI-eligible older? 
            # Insert rev3 unverified superseding rev2
            rev2 = session.scalar(
                select(BankFragment).where(
                    BankFragment.stable_key == "policy_rate_cb_decision",
                    BankFragment.revision == 2,
                )
            )
            assert rev2 is not None
            rev3 = BankFragment(
                id=str(uuid.uuid4()),
                ocr_run_id=rev2.ocr_run_id,
                document_file_id=rev2.document_file_id,
                document_id=rev2.document_id,
                stable_key="policy_rate_cb_decision",
                revision=3,
                kind="exact_quote",
                primary_region_type="unverified",
                content_type="fact",
                content_type_status="unknown",
                page_number=1,
                ocr_text=rev2.ocr_text,
                cleaned_text=None,
                verified_transcript="still there",
                summary_text=None,
                verification_status="verified",
                ocr_correction_json=None,
                source_role=None,
                notes=None,
                supersedes_fragment_id=rev2.id,
                created_at=datetime.now(timezone.utc),
            )
            session.add(rev3)
            session.flush()
            session.add(
                BankFragmentRegion(
                    id=str(uuid.uuid4()),
                    fragment_id=rev3.id,
                    ocr_run_id=run_id,
                    page_number=1,
                    sort_order=0,
                    region_type="unverified",
                    bbox_left=1,
                    bbox_top=1,
                    bbox_width=10,
                    bbox_height=10,
                    coord_space="page_image_px",
                    note=None,
                )
            )
            session.commit()

        with _session(engine) as session:
            ev = retrieve_bank_fragments(
                session,
                query="решение оставить ставку неизменной 14",
                ocr_run_ids=[run_id],
                mode="evidence",
                limit=20,
            )
            # decision key must not appear via rev2 fallback
            keys = [h.stable_key for h in ev.hits]
            assert "policy_rate_cb_decision" not in keys
            cand = retrieve_bank_fragments(
                session,
                query="решение оставить ставку неизменной 14",
                ocr_run_ids=[run_id],
                mode="candidates",
                limit=20,
            )
            decision_hits = [h for h in cand.hits if h.stable_key == "policy_rate_cb_decision"]
            assert len(decision_hits) <= 1
            if decision_hits:
                assert decision_hits[0].revision == 3
                assert decision_hits[0].insufficient_verification
    finally:
        engine.dispose()
        tmp.cleanup()


def test_summary_not_exact_quote(tmp_path: Path):
    tmp, engine, url = _sqlite_migrated()
    try:
        ocr, pdf = _build_valid_corpus(
            tmp_path,
            slug="sum-doc",
            pages=1,
            fragments=[
                {
                    "id": "sum_1",
                    "kind": "summary",
                    "content_type": "interpretation",
                    "content_type_status": "confirmed",
                    "primary_region_type": "prose",
                    "page": 1,
                    "regions": [
                        {
                            "region_type": "prose",
                            "bbox": {"left": 10, "top": 10, "width": 40, "height": 20},
                        }
                    ],
                    "summary": "Банк ожидает сохранения ставки как пересказ.",
                    "verification_status": "verified",
                }
            ],
        )
        staging = stage_corpus(input_dir=ocr, pdf_dir=pdf, staging_parent=tmp_path)
        plan, errs, _ = build_prepared_document(
            staging.ocr_dir / "sum-doc",
            input_dir=staging.ocr_dir,
            pdf_dir=staging.pdf_dir,
            storage_root=staging.storage_root,
        )
        assert plan is not None and not errs
        with _session(engine) as session:
            load_bank_document(session, plan)
            session.commit()
            run_id = session.scalars(select(BankFragment)).one().ocr_run_id
            ev = retrieve_bank_fragments(
                session,
                query="сохранения ставки пересказ",
                ocr_run_ids=[run_id],
                mode="evidence",
                limit=5,
            )
        assert ev.hits
        assert ev.hits[0].text_kind == "summary"
        assert ev.hits[0].eligible_exact_quote is False
    finally:
        engine.dispose()
        tmp.cleanup()


def test_as_of_and_historical_stance(tmp_path: Path):
    tmp, engine, url = _sqlite_migrated()
    try:
        ocr, pdf = _build_valid_corpus(
            tmp_path,
            slug="hist-doc",
            pages=1,
            identity={
                "confirmed_title": "Old steels",
                "confirmed_title_status": "confirmed",
                "confirmed_publication_date": "2021-04-15",
                "confirmed_publication_date_status": "confirmed",
                "confirmed_publication_date_display": "15 April 2021",
                "period_covered_status": "unknown",
                "topics": [],
                "topics_status": "unknown",
                "staleness_note": "Historical 2021 material",
                "is_current_stance": False,
            },
            fragments=[
                _confirmed_fragment(
                    id="steels_note",
                    exact_quote="Ставка и прогноз в историческом материале 2021",
                    ocr_text="Ставка и прогноз в историческом материале 2021",
                )
            ],
        )
        staging = stage_corpus(input_dir=ocr, pdf_dir=pdf, staging_parent=tmp_path)
        plan, errs, _ = build_prepared_document(
            staging.ocr_dir / "hist-doc",
            input_dir=staging.ocr_dir,
            pdf_dir=staging.pdf_dir,
            storage_root=staging.storage_root,
        )
        assert plan is not None and not errs
        with _session(engine) as session:
            load_bank_document(session, plan)
            session.commit()
            run_id = session.scalars(select(BankFragment)).one().ocr_run_id
            future = retrieve_bank_fragments(
                session,
                query="ставка прогноз историческом",
                ocr_run_ids=[run_id],
                mode="evidence",
                as_of_date=date(2020, 1, 1),
                limit=5,
            )
            past = retrieve_bank_fragments(
                session,
                query="ставка прогноз историческом",
                ocr_run_ids=[run_id],
                mode="evidence",
                as_of_date=date(2026, 1, 1),
                limit=5,
            )
        assert future.hits == []
        assert past.hits
        assert past.hits[0].is_current_stance is False
        assert past.hits[0].staleness_note
    finally:
        engine.dispose()
        tmp.cleanup()


def test_run_scope_limit_stability_provenance(tmp_path: Path):
    tmp, engine, url = _sqlite_migrated()
    try:
        _, run_id = _prepare_with_qa(tmp_path, engine)
        with _session(engine) as session:
            with pytest.raises(RetrievalError) as ei:
                retrieve_bank_fragments(
                    session, query="ставка", ocr_run_ids=[], mode="candidates"
                )
            assert ei.value.code == "ocr_run_ids_required"

            a = retrieve_bank_fragments(
                session,
                query="прогноз ставки на конец 2027",
                ocr_run_ids=[run_id],
                mode="evidence",
                limit=2,
            )
            b = retrieve_bank_fragments(
                session,
                query="прогноз ставки на конец 2027",
                ocr_run_ids=[run_id],
                mode="evidence",
                limit=2,
            )
            assert [h.fragment_id for h in a.hits] == [h.fragment_id for h in b.hits]
            assert len(a.hits) <= 2
            if a.hits:
                h = a.hits[0]
                assert h.pdf_sha256
                assert h.ocr_fingerprint_hash
                assert "storage" not in h.text.lower()
                assert not str(h.document_slug).startswith("/")
                # QA provenance separate from source role meaning
                if h.revision >= 2:
                    assert h.qa_method == "ai_vision_over_local_page_png"
                    assert h.source_role == "bank_material_qa_revision"
                    assert "not a direct CB" in h.source_role_meaning.lower() or "bank" in h.source_role_meaning.lower()
    finally:
        engine.dispose()
        tmp.cleanup()
