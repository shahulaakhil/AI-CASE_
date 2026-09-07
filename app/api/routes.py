"""All HTTP endpoints for the ten tools."""
from __future__ import annotations

import io
import json
from typing import Any

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse

from .. import schemas, settings
from ..llm import LLMError, registry as llm
from .byok import bind_client_keys
from ..services import (
    analysis,
    bare_acts,
    documents,
    drafting,
    exports,
    kanoon,
    research,
    tracker,
)

# Every endpoint below resolves the caller's own API keys first, so no handler
# needs to mention the feature.
router = APIRouter(dependencies=[Depends(bind_client_keys)])


def _fail(exc: LLMError) -> HTTPException:
    return HTTPException(status_code=502, detail={"error": exc.to_dict()})


def _turns(history: list[schemas.Turn] | None) -> list[dict]:
    return [{"question": t.question, "answer": t.answer} for t in (history or [])]


def _require_text(text: str, field: str = "text") -> str:
    value = (text or "").strip()
    if not value:
        raise HTTPException(
            status_code=400,
            detail={"error": {"message": f"Provide some {field} to work with."}},
        )
    return value


def _stream(payload: bytes, filename: str, media_type: str) -> StreamingResponse:
    return StreamingResponse(
        io.BytesIO(payload),
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )


# ---------------------------------------------------------------------------
# Platform
# ---------------------------------------------------------------------------


@router.get("/health")
def health() -> dict[str, Any]:
    from .. import db

    return {
        "status": "ok",
        "app": settings.APP_NAME,
        "environment": settings.ENVIRONMENT,
        "providers_configured": [p.id for p in llm.available_providers()],
        "kanoon_connected": kanoon.configured(),
        "storage": db.health(),
    }


@router.get("/config")
def config() -> dict[str, Any]:
    provider_id, model_id = llm.default_selection()
    server_keys = llm.server_providers()
    return {
        "app_name": settings.APP_NAME,
        "tagline": settings.APP_TAGLINE,
        "providers": llm.all_status(),
        "default_provider": provider_id,
        "default_model": model_id,
        "any_provider": llm.any_available(),
        "kanoon_connected": kanoon.configured(),
        # Bring your own key state. "byok_only" tells the front end that this
        # deployment ships no keys of its own, so the first thing a visitor
        # needs to do is paste one.
        "allow_client_keys": settings.ALLOW_CLIENT_KEYS,
        "byok_only": settings.ALLOW_CLIENT_KEYS and not server_keys,
        "server_providers": server_keys,
        "client_providers": llm.client_providers(),
        "server_kanoon": bool(settings.INDIAN_KANOON_API_TOKEN),
        "max_upload_mb": settings.MAX_UPLOAD_MB,
        "max_ocr_pages": settings.MAX_OCR_PAGES,
        "doc_types": drafting.DOC_TYPES,
        "case_statuses": list(tracker.STATUSES),
        "case_priorities": list(tracker.PRIORITIES),
        "acts_stats": bare_acts.stats(),
        "supported_uploads": sorted(documents.SUPPORTED_EXTENSIONS),
    }


@router.post("/providers/verify")
def providers_verify(payload: schemas.VerifyRequest) -> dict[str, Any]:
    """Check one provider's key against the provider itself.

    The key is whatever the caller sent in this request's header, so a visitor
    who has just pasted their own key finds out immediately whether it works
    rather than at the end of a long drafting run.
    """
    provider = llm.provider_map().get(payload.provider.strip().lower())
    if provider is None:
        raise HTTPException(
            status_code=404,
            detail={"error": {"message": f"Unknown provider '{payload.provider}'."}},
        )
    try:
        models = provider.verify()
    except LLMError as exc:
        raise _fail(exc) from exc
    status = provider.status().as_dict()
    return {
        "ok": True,
        "provider": provider.id,
        "label": provider.label,
        "key_source": provider.key_source,
        "callable_models": len(models),
        "models": status["models"],
        "default_model": status["default_model"],
    }


@router.post("/providers/verify/kanoon")
def providers_verify_kanoon() -> dict[str, Any]:
    """Check an Indian Kanoon token with one small search."""
    if not kanoon.configured():
        raise HTTPException(
            status_code=400,
            detail={"error": {"message": "No Indian Kanoon token was supplied."}},
        )
    result = kanoon.search("constitution of india", page=0)
    found = bool(result.get("docs"))
    return {
        "ok": found,
        "message": (
            f"Indian Kanoon is connected. A test search matched {result.get('total_count', 0)} "
            "judgments."
            if found
            else result.get("note")
            or "The token was sent but Indian Kanoon returned nothing for a test search."
        ),
    }


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------


@router.post("/extract")
async def extract(
    file: UploadFile = File(...),
    provider: str = Form(default=""),
    model: str = Form(default=""),
    force_ocr: bool = Form(default=False),
) -> dict[str, Any]:
    payload = await file.read()
    size_mb = len(payload) / (1024 * 1024)
    if size_mb > settings.MAX_UPLOAD_MB:
        raise HTTPException(
            status_code=413,
            detail={
                "error": {
                    "message": (
                        f"That file is {size_mb:.1f} MB. The limit is "
                        f"{settings.MAX_UPLOAD_MB} MB."
                    )
                }
            },
        )
    if not payload:
        raise HTTPException(
            status_code=400, detail={"error": {"message": "The uploaded file is empty."}}
        )

    try:
        result = documents.extract(
            payload,
            file.filename or "document",
            provider=provider or None,
            model=model or None,
            force_ocr=force_ocr,
        )
    except LLMError as exc:
        raise _fail(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"error": {"message": str(exc)}}) from exc
    except Exception as exc:  # noqa: BLE001 - surface a readable message
        raise HTTPException(
            status_code=422,
            detail={
                "error": {
                    "message": f"That file could not be read: {exc}",
                    "hint": "Try re-saving it as a PDF, or paste the text directly.",
                }
            },
        ) from exc

    if not result.text.strip():
        result.warnings.append(
            "No readable text was found. If this is a scan, choose a provider with a "
            "vision model and try again with OCR forced."
        )
    return result.as_dict()


@router.post("/extract/check")
async def extract_check(file: UploadFile = File(...)) -> dict[str, Any]:
    payload = await file.read()
    try:
        return {
            "needs_vision": documents.needs_vision(payload, file.filename or ""),
            "filename": file.filename,
            "size_bytes": len(payload),
        }
    except Exception:  # noqa: BLE001
        return {"needs_vision": True, "filename": file.filename, "size_bytes": len(payload)}


# ---------------------------------------------------------------------------
# Tool 1: List of Dates
# ---------------------------------------------------------------------------


@router.post("/tools/list-of-dates")
def tool_list_of_dates(request: schemas.DatesRequest) -> dict[str, Any]:
    text = _require_text(request.text, "document text")
    try:
        rows = analysis.list_of_dates(
            text,
            case_title=request.case_title,
            provider=request.provider,
            model=request.model,
        )
    except LLMError as exc:
        raise _fail(exc) from exc
    return {"rows": rows, "case_title": request.case_title, "count": len(rows)}


# ---------------------------------------------------------------------------
# Tool 2: Legal Research
# ---------------------------------------------------------------------------


@router.post("/tools/research")
def tool_research(request: schemas.ResearchRequest) -> dict[str, Any]:
    question = _require_text(request.question, "question")
    try:
        return research.research(
            question,
            max_results=request.max_results,
            history=_turns(request.history),
            provider=request.provider,
            model=request.model,
        )
    except LLMError as exc:
        raise _fail(exc) from exc


@router.post("/tools/research/document")
def tool_research_document(request: schemas.DocumentQuestionRequest) -> dict[str, Any]:
    question = _require_text(request.question, "question")
    text = _require_text(request.document_text, "document text")
    try:
        answer = research.ask_document(
            question,
            text,
            document_name=request.document_name,
            history=_turns(request.history),
            provider=request.provider,
            model=request.model,
        )
    except LLMError as exc:
        raise _fail(exc) from exc
    return {"answer": answer, "sources": [], "intent": "DOCUMENT"}


@router.get("/tools/kanoon/search")
def tool_kanoon_search(q: str = Query(..., min_length=2), page: int = 0) -> dict[str, Any]:
    return kanoon.search(q, page=page)


# ---------------------------------------------------------------------------
# Tool 3: Authority Check
# ---------------------------------------------------------------------------


@router.post("/tools/authority-check")
def tool_authority_check(request: schemas.AuthorityRequest) -> dict[str, Any]:
    citation = _require_text(request.citation, "citation")
    try:
        return analysis.check_authority(
            citation, provider=request.provider, model=request.model
        )
    except LLMError as exc:
        raise _fail(exc) from exc


# ---------------------------------------------------------------------------
# Tool 4: Translation and document chat
# ---------------------------------------------------------------------------


@router.post("/tools/translate")
def tool_translate(request: schemas.TranslateRequest) -> dict[str, Any]:
    text = _require_text(request.text, "document text")
    try:
        language = request.source_language
        if request.detect and not language:
            language = research.detect_language(
                text, provider=request.provider, model=request.model
            )

        already_english = language.strip().lower() in ("english", "en", "unknown", "")
        translation = ""
        if not already_english:
            translation = research.translate_to_english(
                text,
                source_language=language,
                provider=request.provider,
                model=request.model,
            )
    except LLMError as exc:
        raise _fail(exc) from exc

    return {
        "language": language or "unknown",
        "translation": translation,
        "already_english": already_english,
    }


@router.post("/tools/document-chat")
def tool_document_chat(request: schemas.DocumentChatRequest) -> dict[str, Any]:
    question = _require_text(request.question, "question")
    _require_text(request.original_text or request.translated_text, "document text")
    try:
        answer = research.chat_with_document(
            question,
            request.original_text,
            request.translated_text,
            history=_turns(request.history),
            provider=request.provider,
            model=request.model,
        )
    except LLMError as exc:
        raise _fail(exc) from exc
    return {"answer": answer}


# ---------------------------------------------------------------------------
# Tool 5: Prompt Enhancer
# ---------------------------------------------------------------------------


@router.post("/tools/enhance-prompt")
def tool_enhance_prompt(request: schemas.EnhanceRequest) -> dict[str, Any]:
    query = _require_text(request.query, "question")
    try:
        return research.enhance_prompt(query, provider=request.provider, model=request.model)
    except LLMError as exc:
        raise _fail(exc) from exc


# ---------------------------------------------------------------------------
# Tool 6: Document Drafter
# ---------------------------------------------------------------------------


@router.post("/tools/draft")
def tool_draft(request: schemas.DraftRequest) -> dict[str, Any]:
    facts = _require_text(request.facts, "facts")
    if request.doc_type not in drafting.DOC_TYPE_NAMES:
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "message": f"Unknown document type '{request.doc_type}'.",
                    "hint": "Pick one of: " + ", ".join(drafting.DOC_TYPE_NAMES),
                }
            },
        )
    try:
        draft = drafting.draft_document(
            request.doc_type,
            facts,
            petitioner=request.petitioner,
            respondent=request.respondent,
            court=request.court,
            reliefs=request.reliefs,
            extra_instructions=request.extra_instructions,
            provider=request.provider,
            model=request.model,
        )
    except LLMError as exc:
        raise _fail(exc) from exc

    citations = drafting.extract_citations(draft)
    return {
        "draft": draft,
        "clean_draft": drafting.strip_citation_markers(draft),
        "citations": citations,
        "verify_count": sum(1 for c in citations if c["needs_verification"]),
        "doc_type": request.doc_type,
    }


# ---------------------------------------------------------------------------
# Tool 7: Court Tracker
# ---------------------------------------------------------------------------


@router.get("/cases")
def cases_list() -> dict[str, Any]:
    return {"cases": tracker.list_cases(), "summary": tracker.summary()}


@router.post("/cases", status_code=201)
def cases_create(payload: schemas.CaseCreate) -> dict[str, Any]:
    if not payload.case_name.strip():
        raise HTTPException(
            status_code=400, detail={"error": {"message": "A case name is required."}}
        )
    return tracker.create_case(payload.model_dump())


@router.patch("/cases/{case_id}")
def cases_update(case_id: str, payload: schemas.CaseUpdate) -> dict[str, Any]:
    updated = tracker.update_case(
        case_id, {k: v for k, v in payload.model_dump().items() if v is not None}
    )
    if updated is None:
        raise HTTPException(status_code=404, detail={"error": {"message": "Case not found."}})
    return updated


@router.delete("/cases/{case_id}")
def cases_delete(case_id: str) -> dict[str, Any]:
    if not tracker.delete_case(case_id):
        raise HTTPException(status_code=404, detail={"error": {"message": "Case not found."}})
    return {"deleted": case_id}


@router.post("/cases/{case_id}/hearings")
def cases_add_hearing(case_id: str, payload: schemas.HearingCreate) -> dict[str, Any]:
    updated = tracker.add_hearing(case_id, payload.date, payload.outcome, payload.next_date)
    if updated is None:
        raise HTTPException(status_code=404, detail={"error": {"message": "Case not found."}})
    return updated


@router.delete("/cases/{case_id}/hearings/{hearing_id}")
def cases_delete_hearing(case_id: str, hearing_id: str) -> dict[str, Any]:
    updated = tracker.delete_hearing(case_id, hearing_id)
    if updated is None:
        raise HTTPException(status_code=404, detail={"error": {"message": "Case not found."}})
    return updated


@router.get("/cases/upcoming")
def cases_upcoming(days: int = 30) -> dict[str, Any]:
    return {
        "upcoming": tracker.upcoming(days),
        "overdue": tracker.overdue(),
        "summary": tracker.summary(),
    }


@router.post("/cases/ecourts")
def cases_ecourts(payload: schemas.CnrRequest) -> dict[str, Any]:
    return tracker.fetch_ecourts_status(payload.cnr)


# ---------------------------------------------------------------------------
# Tool 8: Judgment Summariser
# ---------------------------------------------------------------------------


@router.post("/tools/summarise")
def tool_summarise(request: schemas.SummariseRequest) -> dict[str, Any]:
    text = _require_text(request.text, "judgment text")
    try:
        brief = analysis.summarise_judgment(
            text, provider=request.provider, model=request.model
        )
    except LLMError as exc:
        raise _fail(exc) from exc
    return {"brief": brief}


# ---------------------------------------------------------------------------
# Tool 9: Bare Acts
# ---------------------------------------------------------------------------


@router.get("/acts")
def acts_list() -> dict[str, Any]:
    return {
        "acts": bare_acts.list_acts(),
        "categories": bare_acts.categories(),
        "stats": bare_acts.stats(),
    }


@router.get("/acts/search")
def acts_search(q: str = Query(..., min_length=2)) -> dict[str, Any]:
    results = bare_acts.search_sections(q)
    return {"results": results, "count": len(results), "query": q}


@router.get("/acts/detail")
def acts_detail(name: str = Query(...)) -> dict[str, Any]:
    detail = bare_acts.act_detail(name)
    if detail is None:
        raise HTTPException(status_code=404, detail={"error": {"message": "Act not found."}})
    return detail


@router.post("/acts/ask")
def acts_ask(request: schemas.ProvisionRequest) -> dict[str, Any]:
    question = _require_text(request.question, "question")
    try:
        return bare_acts.ask_provision(
            request.act,
            request.section,
            question,
            provider=request.provider,
            model=request.model,
        )
    except LLMError as exc:
        raise _fail(exc) from exc


# ---------------------------------------------------------------------------
# Tool 10: Counter Arguments
# ---------------------------------------------------------------------------


@router.post("/tools/counter/claims")
def tool_counter_claims(request: schemas.ClaimsRequest) -> dict[str, Any]:
    text = _require_text(request.text, "document text")
    try:
        claims = drafting.extract_claims(
            text, provider=request.provider, model=request.model
        )
    except LLMError as exc:
        raise _fail(exc) from exc
    return {"claims": claims, "count": len(claims)}


@router.post("/tools/counter/draft")
def tool_counter_draft(request: schemas.CounterRequest) -> dict[str, Any]:
    claim = _require_text(request.claim, "claim")
    try:
        return drafting.draft_counter(
            claim,
            request.legal_basis,
            request.context,
            provider=request.provider,
            model=request.model,
        )
    except LLMError as exc:
        raise _fail(exc) from exc


@router.post("/tools/counter/draft-all")
def tool_counter_draft_all(request: schemas.CountersRequest) -> dict[str, Any]:
    if not request.claims:
        raise HTTPException(
            status_code=400, detail={"error": {"message": "Extract some claims first."}}
        )
    try:
        counters = drafting.draft_all_counters(
            [claim.model_dump() for claim in request.claims],
            provider=request.provider,
            model=request.model,
        )
    except LLMError as exc:
        raise _fail(exc) from exc
    return {"counters": counters, "count": len(counters)}


@router.post("/tools/counter/assemble")
def tool_counter_assemble(request: schemas.AssembleRequest) -> dict[str, Any]:
    if not request.counters:
        raise HTTPException(
            status_code=400,
            detail={"error": {"message": "Draft the counter arguments before assembling."}},
        )
    try:
        text = drafting.assemble_written_statement(
            request.counters,
            petitioner=request.petitioner,
            respondent=request.respondent,
            court=request.court,
            extra_defences=request.extra_defences,
            provider=request.provider,
            model=request.model,
        )
    except LLMError as exc:
        raise _fail(exc) from exc
    citations = drafting.extract_citations(text)
    return {"draft": text, "citations": citations}


@router.post("/tools/counter/ask")
def tool_counter_ask(request: schemas.ClaimQuestionRequest) -> dict[str, Any]:
    question = _require_text(request.question, "question")
    try:
        answer = drafting.ask_about_claim(
            question,
            request.claim,
            request.counter,
            provider=request.provider,
            model=request.model,
        )
    except LLMError as exc:
        raise _fail(exc) from exc
    return {"answer": answer}


# ---------------------------------------------------------------------------
# Exports
# ---------------------------------------------------------------------------

_MEDIA = {
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pdf": "application/pdf",
    "csv": "text/csv; charset=utf-8",
    "txt": "text/plain; charset=utf-8",
    "md": "text/markdown; charset=utf-8",
}


def _flatten_brief(brief: dict) -> str:
    details = brief.get("case_details") or {}
    lines: list[str] = []
    for label, key in (
        ("Case", "case_name"),
        ("Citation", "citation"),
        ("Court", "court"),
        ("Bench", "bench"),
        ("Date of judgment", "date_of_judgment"),
        ("Subject matter", "subject_matter"),
    ):
        if details.get(key):
            lines.append(f"{label}: {details[key]}")
    for label, key in (
        ("FACTS", "facts"),
        ("ISSUES FRAMED", "issues"),
        ("ARGUMENTS FOR THE PETITIONER", "petitioner_arguments"),
        ("ARGUMENTS FOR THE RESPONDENT", "respondent_arguments"),
        ("HELD", "held"),
        ("RATIO DECIDENDI", "ratio"),
        ("SIGNIFICANCE", "significance"),
        ("KEY STATUTES CITED", "key_statutes_cited"),
        ("KEY CASES CITED", "key_cases_cited"),
    ):
        value = brief.get(key)
        if not value:
            continue
        lines.append("")
        lines.append(label)
        if isinstance(value, list):
            lines.extend(f"- {item}" for item in value)
        else:
            lines.append(str(value))
    return "\n".join(lines)


def _flatten_dates(rows: list[dict]) -> str:
    lines = []
    for row in rows:
        lines.append(f"{row.get('date', '')}  |  {row.get('event', '')}")
        detail = " | ".join(
            part for part in (row.get("source", ""), row.get("significance", "")) if part
        )
        if detail:
            lines.append(f"    {detail}")
    return "\n".join(lines)


@router.post("/export")
def export(request: schemas.ExportRequest = Body(...)) -> StreamingResponse:
    kind = request.kind
    fmt = request.format
    payload = request.payload or {}
    title = request.title or "LitigatAI export"
    subtitle = request.subtitle
    body = request.body

    try:
        if kind == "list-of-dates":
            rows = payload.get("rows") or []
            case_title = payload.get("case_title", "")
            if fmt == "csv":
                data = exports.list_of_dates_csv(rows)
            elif fmt == "docx":
                data = exports.list_of_dates_docx(rows, case_title)
            else:
                data = _render_text(fmt, "List of Dates and Events", _flatten_dates(rows),
                                    case_title)
        elif kind == "judgment-brief":
            brief = payload.get("brief") or {}
            name = (brief.get("case_details") or {}).get("case_name", "")
            if fmt == "docx":
                data = exports.judgment_brief_docx(brief, name)
            else:
                data = _render_text(fmt, "Judgment Brief", _flatten_brief(brief), name)
        elif kind == "legal-document":
            doc_type = payload.get("doc_type", title)
            content = payload.get("content", body)
            if fmt == "docx":
                data = exports.legal_document_docx(
                    doc_type,
                    content,
                    case_title=payload.get("case_title", ""),
                    court=payload.get("court", ""),
                )
            else:
                data = _render_text(fmt, doc_type, content, payload.get("case_title", ""))
        elif kind == "research-note":
            question = payload.get("question", "")
            answer = payload.get("answer", body)
            sources = payload.get("sources") or []
            if fmt == "docx":
                data = exports.research_answer_docx(question, answer, sources)
            else:
                combined = f"QUESTION\n{question}\n\nANSWER\n{answer}"
                if sources:
                    combined += "\n\nSOURCES\n" + "\n".join(
                        f"[{s.get('n', '')}] {s.get('title', '')}" for s in sources
                    )
                data = _render_text(fmt, "Legal Research Note", combined)
        elif kind == "authority-report":
            result = payload.get("result") or {}
            if fmt == "docx":
                data = exports.authority_report_docx(result)
            else:
                text = (
                    f"Citation: {result.get('citation_searched', '')}\n"
                    f"Status: {result.get('status', '')}\n"
                    f"Confidence: {result.get('confidence', '')}\n\n"
                    f"{result.get('summary', '')}"
                )
                data = _render_text(fmt, "Authority Check Report", text)
        elif kind == "translation":
            if fmt == "docx":
                data = exports.translation_docx(
                    payload.get("original", ""),
                    payload.get("translated", ""),
                    language=payload.get("language", ""),
                    filename=payload.get("filename", ""),
                )
            else:
                combined = payload.get("translated", "") or payload.get("original", "")
                data = _render_text(fmt, "Translated Legal Document", combined, subtitle)
        elif kind == "counter-arguments":
            counters = payload.get("counters") or []
            if fmt == "docx":
                data = exports.counter_arguments_docx(counters, payload.get("case_title", ""))
            else:
                text = "\n\n".join(
                    f"CLAIM {c.get('claim_id', '')}: {c.get('original_claim', '')}\n"
                    f"{c.get('counter_argument', '')}"
                    for c in counters
                )
                data = _render_text(fmt, "Counter Argument Analysis", text)
        elif kind == "cases":
            cases = payload.get("cases") or tracker.list_cases()
            if fmt == "csv":
                data = exports.cases_csv(cases)
            else:
                text = "\n".join(
                    f"{c.get('next_date', 'no date')}  {c.get('case_name', '')}  "
                    f"{c.get('court', '')}  [{c.get('status', '')}]"
                    for c in cases
                )
                data = _render_text(fmt, "Case Diary", text)
        else:
            data = _render_text(fmt, title, body, subtitle)
    except Exception as exc:  # noqa: BLE001 - export failures must be readable
        raise HTTPException(
            status_code=500,
            detail={"error": {"message": f"The export could not be built: {exc}"}},
        ) from exc

    extension = "csv" if fmt == "csv" else fmt
    filename = exports.safe_filename(request.filename or title or kind, extension)
    return _stream(data, filename, _MEDIA.get(fmt, "application/octet-stream"))


def _render_text(fmt: str, title: str, body: str, subtitle: str = "") -> bytes:
    if fmt == "pdf":
        return exports.pdf_from_text(title, body, subtitle)
    if fmt == "docx":
        return exports.plain_docx(title, body, subtitle)
    if fmt == "md":
        header = f"# {title}\n\n"
        if subtitle:
            header += f"_{subtitle}_\n\n"
        return (header + body).encode("utf-8")
    if fmt == "csv":
        return body.encode("utf-8-sig")
    header = f"{title.upper()}\n"
    if subtitle:
        header += f"{subtitle}\n"
    header += "=" * min(len(title), 70) + "\n\n"
    return (header + body).encode("utf-8")


@router.post("/export/raw")
def export_raw(payload: dict[str, Any] = Body(...)) -> StreamingResponse:
    """Download arbitrary text the UI is already showing, in txt or md."""
    fmt = payload.get("format", "txt")
    if fmt not in ("txt", "md", "json"):
        fmt = "txt"
    body = payload.get("body", "")
    if fmt == "json":
        data = json.dumps(payload.get("payload", {}), indent=2, ensure_ascii=False).encode("utf-8")
        media = "application/json"
    else:
        data = _render_text(fmt, payload.get("title", "LitigatAI"), body)
        media = _MEDIA.get(fmt, "text/plain; charset=utf-8")
    filename = exports.safe_filename(payload.get("filename", "litigatai"), fmt)
    return _stream(data, filename, media)
