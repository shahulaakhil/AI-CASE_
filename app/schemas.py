"""Request and response models."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ModelChoice(BaseModel):
    """Every AI backed request carries the provider and model chosen in the UI."""

    provider: str | None = Field(default=None, description="Provider id, for example groq")
    model: str | None = Field(default=None, description="Model id for that provider")


class Turn(BaseModel):
    question: str = ""
    answer: str = ""


# --- Tool 1 ---------------------------------------------------------------


class DatesRequest(ModelChoice):
    text: str
    case_title: str = ""


class DateRow(BaseModel):
    date: str = ""
    event: str = ""
    source: str = ""
    significance: str = ""


class DatesResponse(BaseModel):
    rows: list[DateRow]
    case_title: str = ""


# --- Tool 2 ---------------------------------------------------------------


class ResearchRequest(ModelChoice):
    question: str
    max_results: int = 5
    history: list[Turn] = Field(default_factory=list)


class DocumentQuestionRequest(ModelChoice):
    question: str
    document_text: str
    document_name: str = ""
    history: list[Turn] = Field(default_factory=list)


# --- Tool 3 ---------------------------------------------------------------


class AuthorityRequest(ModelChoice):
    citation: str


# --- Tool 4 ---------------------------------------------------------------


class TranslateRequest(ModelChoice):
    text: str
    source_language: str = ""
    detect: bool = True


class DocumentChatRequest(ModelChoice):
    question: str
    original_text: str
    translated_text: str = ""
    history: list[Turn] = Field(default_factory=list)


# --- Tool 5 ---------------------------------------------------------------


class EnhanceRequest(ModelChoice):
    query: str


# --- Tool 6 ---------------------------------------------------------------


class DraftRequest(ModelChoice):
    doc_type: str
    facts: str
    petitioner: str = ""
    respondent: str = ""
    court: str = ""
    reliefs: str = ""
    extra_instructions: str = ""


# --- Tool 7 ---------------------------------------------------------------


class CaseCreate(BaseModel):
    case_name: str
    court: str = ""
    case_number: str = ""
    cnr_number: str = ""
    parties: str = ""
    next_date: str = ""
    stage: str = ""
    status: str = "Pending"
    priority: str = "Normal"
    notes: str = ""


class CaseUpdate(BaseModel):
    case_name: str | None = None
    court: str | None = None
    case_number: str | None = None
    cnr_number: str | None = None
    parties: str | None = None
    next_date: str | None = None
    stage: str | None = None
    status: str | None = None
    priority: str | None = None
    notes: str | None = None


class HearingCreate(BaseModel):
    date: str
    outcome: str = ""
    next_date: str = ""


class CnrRequest(BaseModel):
    cnr: str


# --- Tool 8 ---------------------------------------------------------------


class SummariseRequest(ModelChoice):
    text: str


# --- Tool 9 ---------------------------------------------------------------


class ProvisionRequest(ModelChoice):
    act: str
    section: str = ""
    question: str


# --- Tool 10 --------------------------------------------------------------


class ClaimsRequest(ModelChoice):
    text: str


class Claim(BaseModel):
    claim_id: str = ""
    claim: str = ""
    legal_basis: str = ""
    key_facts: str = ""
    strength: str = "MODERATE"


class CounterRequest(ModelChoice):
    claim: str
    legal_basis: str = ""
    context: str = ""


class CountersRequest(ModelChoice):
    claims: list[Claim]


class AssembleRequest(ModelChoice):
    counters: list[dict[str, Any]]
    petitioner: str = ""
    respondent: str = ""
    court: str = ""
    extra_defences: str = ""


class ClaimQuestionRequest(ModelChoice):
    question: str
    claim: str
    counter: str = ""


# --- Provider keys ---------------------------------------------------------


class VerifyRequest(BaseModel):
    """Which provider's credential to check. The key itself rides in a header."""

    provider: str


# --- Exports ---------------------------------------------------------------


ExportFormat = Literal["docx", "pdf", "csv", "txt", "md"]


class ExportRequest(BaseModel):
    kind: str
    format: ExportFormat = "docx"
    title: str = ""
    subtitle: str = ""
    filename: str = ""
    body: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)
