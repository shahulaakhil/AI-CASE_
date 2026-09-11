"""Document Drafter and Counter Arguments."""
from __future__ import annotations

import re
from typing import Any

from ..llm import registry as llm
from .documents import clip

# ---------------------------------------------------------------------------
# Tool 6: Document Drafter
# ---------------------------------------------------------------------------

DOC_TYPES: list[dict[str, str]] = [
    {
        "id": "plaint",
        "name": "Suit (Plaint)",
        "family": "Court filing",
        "description": "Civil suit under Order VII CPC with cause title, jurisdiction, limitation and prayer.",
    },
    {
        "id": "statement_of_claims",
        "name": "Statement of Claims",
        "family": "Arbitration",
        "description": "Claimant's pleading under the Arbitration and Conciliation Act 1996.",
    },
    {
        "id": "written_statement",
        "name": "Written Statement",
        "family": "Court filing",
        "description": "Defence under Order VIII CPC with preliminary objections and para wise reply.",
    },
    {
        "id": "statement_of_defense",
        "name": "Statement of Defense",
        "family": "Arbitration",
        "description": "Respondent's arbitration pleading with objections and positive case.",
    },
    {
        "id": "rejoinder",
        "name": "Rejoinder",
        "family": "Either",
        "description": "Rebuttal to a Written Statement or Statement of Defense.",
    },
    {
        "id": "vakalatnama",
        "name": "Vakalatnama",
        "family": "Court filing",
        "description": "Power of attorney appointing an advocate, in standard Indian court form.",
    },
    {
        "id": "counter_claim",
        "name": "Counter-Claim",
        "family": "Court filing",
        "description": "Independent claim under Order VIII Rule 6A CPC filed with the defence.",
    },
    {
        "id": "legal_notice",
        "name": "Legal Notice",
        "family": "Pre litigation",
        "description": "Demand notice before suit, including statutory notice periods.",
    },
    {
        "id": "application",
        "name": "Application / Misc. Petition",
        "family": "Court filing",
        "description": "Interlocutory application, for example injunction, stay or condonation.",
    },
]

DOC_TYPE_NAMES = [item["name"] for item in DOC_TYPES]

_DRAFT_SYSTEM = """You are a senior advocate of the Supreme Court of India with twenty years of
drafting experience across civil litigation, commercial disputes and arbitration.

FORMAT RULES, FOLLOW EXACTLY

1. PARAGRAPH NUMBERING
   Court filings (Plaint, Written Statement, Counter-Claim, Application): plain Arabic
   numbering, 1., 2., 3., with each paragraph opening with the word "That".
   Arbitration documents (Statement of Claims, Statement of Defense, Rejoinder): decimal
   numbering, 1.1, 1.2, 2.1, under Roman numeral section headings.

2. SECTION STRUCTURE for arbitration and complex pleadings
   I.   INTRODUCTION AND BACKGROUND
   II.  PRELIMINARY SUBMISSIONS OR PRELIMINARY OBJECTIONS
   III. FACTUAL MATRIX
   IV.  LEGAL SUBMISSIONS, with lettered sub headings A, B, C for each distinct ground
   V.   RELIEFS SOUGHT

3. DEFINED TERMS
   On first mention define the short form in brackets, for example
   ABC Private Limited (hereinafter "the Claimant"), and use it consistently thereafter.

4. ANNEXURE CROSS REFERENCES
   Mark them in the body in square brackets, for example [Annexure A], [Annexure C-3].
   Close the document with an ANNEXURES list giving one line per annexure.

5. INLINE CITATIONS
   Use [CITE: source] markers, and only for:
   statutes, for example [CITE: CPC s.9], [CITE: A&C Act 1996 s.34], [CITE: ICA 1872 s.73];
   case law, for example [CITE: Case Name (Year) Citation], only where the case is real and
   you are confident of it;
   anything uncertain, written as [CITE: verify - what needs checking].
   Never invent a citation. Mark every uncertain one as verify.
   Every jurisdictional averment, every limitation averment and every legal proposition
   must carry a marker. A pleading that contains no [CITE: ...] markers is incomplete.

6. FORMAL LANGUAGE
   Court filings open the body with "MOST RESPECTFULLY SHOWETH:".
   Arbitration pleadings open with "RESPECTFULLY SUBMITTED THAT:".
   Close the pleading with WHEREFORE and a PRAYER.

7. CLOSING BLOCK after the prayer
   VERIFICATION for court filings, sworn by the party.
   AFFIDAVIT where the court rules require one.
   Filed through: [Counsel's name], Advocate. Enrolment No.: ______.
   Date: ______   Place: ______

8. QUALITY
   Keep a formal, third person, impersonal register throughout.
   Use a table where comparing dates, quantities or figures.
   Put defined terms and annexure references in bold.
   Output only the document itself, with no commentary before or after it."""

_VAKALATNAMA_SYSTEM = """Draft a Vakalatnama, the power of attorney appointing an advocate, in the
form used across Indian courts. Include the court name and case details as fillable blanks, the
client's name, address and description, the advocate's name and enrolment number, the full list
of standard powers granted (to file, plead, appear, compromise, withdraw, appeal, receive money
and execute decrees), an acceptance clause signed by the advocate, an attestation block before a
Notary or Oath Commissioner, and signature, date and place blocks. Output only the document."""

_DOC_INSTRUCTIONS: dict[str, str] = {
    "Suit (Plaint)": """Draft a Plaint for filing before an Indian civil court.

Required sections:
1. Court heading: "IN THE COURT OF [court name]" with a suit number placeholder.
2. Cause title: plaintiff details against defendant details, with full addresses.
3. Body under Order VII CPC:
   Para 1: who the plaintiff is, occupation and address.
   Para 2: jurisdiction, territorial [CITE: CPC s.20], pecuniary and subject matter.
   Para 3 onwards: chronological facts with dates, amounts and annexure references.
   Second last para: limitation, the date the cause of action arose, and the applicable
   Article of the Limitation Act 1963.
   Last para: valuation of the suit and court fee paid.
4. Prayer with lettered sub clauses a), b), c) for each relief, including interest and costs.
5. Verification, para wise and sworn by the plaintiff.
6. Annexures list.

Numbering: plain Arabic. Every paragraph opens with "That".""",
    "Statement of Claims": """Draft a Statement of Claims in an arbitration under the Arbitration and
Conciliation Act 1996.

I. INTRODUCTION
   1.1 The parties, with defined terms.
   1.2 The arbitration agreement and the constitution of the Tribunal.
   1.3 The dispute in two or three sentences.
II. FACTUAL BACKGROUND
   2.1 onwards, chronological, each supporting document marked [Annexure C-N].
   Use a table where comparing deliveries, payments or timelines.
III. LEGAL FRAMEWORK
   3.1 Governing law, seat and jurisdiction [CITE: A&C Act 1996 s.7, s.11 as applicable].
   3.2 Applicable substantive law with sections.
IV. CLAIMS
   A. CLAIM I, with a heading naming the breach, then 4.1 onwards giving the factual and
      legal basis and the computation of quantum.
   B. CLAIM II, and further claims as the facts warrant.
V. RELIEF CLAIMED
   a) Principal damages [CITE: ICA 1872 s.73].
   b) Interest at the stated rate [CITE: A&C Act 1996 s.31(7)].
   c) Costs of the arbitration.
   d) Any other relief the Tribunal thinks just.
Verification. Annexures in the C-N series.

Numbering: decimal.""",
    "Written Statement": """Draft a Written Statement under Order VIII CPC.

PRELIMINARY OBJECTIONS, numbered I, II, III:
   Maintainability and jurisdiction, limitation [CITE: Limitation Act 1963], non joinder or
   mis joinder of parties, and any other threshold objection.
PARA WISE REPLY:
   For every paragraph of the plaint write a matching reply, in the form
   "Re Para 1: The contents of Para 1 are admitted to the extent that ... and are otherwise
   denied." Follow each denial with the defendant's positive version.
DEFENDANT'S POSITIVE CASE:
   Lettered sub headings A, B, C for each substantive defence, for example accord and
   satisfaction, estoppel, waiver, force majeure.
COUNTER-CLAIM if the facts support one, drafted under Order VIII Rule 6A CPC with its own
   prayer.
PRAYER to dismiss the suit with costs.
Verification. Annexures in the D-N series.

Numbering: plain Arabic. Every paragraph opens with "That".""",
    "Statement of Defense": """Draft a Statement of Defense in an arbitration under the Arbitration
and Conciliation Act 1996.

I. INTRODUCTION with the parties and the respondent's overall position.
II. PRELIMINARY OBJECTIONS
   A. Jurisdiction and maintainability [CITE: A&C Act 1996 s.16].
   B. Limitation [CITE: Limitation Act 1963].
   C. Any further threshold objection.
III. RESPONSE TO THE CLAIMANT'S FACTUAL BACKGROUND
   3.1 onwards, in the form "In response to paragraph X of the Statement of Claims, the
   Respondent states that ...". Mark defence documents as [Annexure R-N].
IV. RESPONDENT'S POSITIVE CASE, lettered A, B, C, with any counter claim and its quantum.
V. RELIEF SOUGHT: dismissal of all claims, counter claim relief if any, and costs.
Verification. Annexures in the R-N series.

Numbering: decimal.""",
    "Rejoinder": """Draft a Rejoinder replying to a Written Statement or Statement of Defense. This is
a rebuttal. Answer each submission sharply and reinforce the original case.

I. INTRODUCTION identifying the pleading replied to and its date, and stating that everything
   in it is denied save what is expressly admitted below.
II. REPLY TO PRELIMINARY OBJECTIONS, lettered A, B, C, each rebutted with authority.
III. PARA WISE REPLY, in the form "Re Para 1 of the Written Statement: ...", adding legal
   argument where it helps. Mark new evidence as [Annexure C-N].
IV. LEGAL SUBMISSIONS IN REJOINDER, lettered A, B, C, each with citations.
V. PRAYER to reject the objections, affirm the original reliefs, and grant costs.
Verification. Annexures list.

Numbering: decimal.""",
    "Counter-Claim": """Draft a Counter-Claim under Order VIII Rule 6A CPC, filed with the Written
Statement.

Cause title with the defendant shown as counter claimant.
1. That the counter claimant is the defendant in the captioned suit
   [CITE: CPC Order VIII Rule 6A].
2. That beyond the defence taken, the counter claimant has an independent cause of action
   against the plaintiff arising from the facts set out below.
3 onwards: the facts of the counter claim, chronological, with annexures in the D-N series.
Second last para: limitation and jurisdiction for the counter claim.
Last para: valuation and court fee.
PRAYER with lettered reliefs including interest and costs.
Verification.

Numbering: plain Arabic. Every paragraph opens with "That". Keep the counter claim facts
clearly separate from the defence.""",
    "Legal Notice": """Draft a legal notice to be sent before instituting proceedings.

Letterhead block for the advocate, the date, and the mode of service.
Addressee block with the full name and address of the noticee.
Subject line naming the dispute in one sentence.
Body:
1. That the notice is issued under instructions from the client, who is described in full.
2. Chronological facts with dates, amounts and references to documents.
3. The breach or wrong complained of, with the legal provision it offends.
4. The loss suffered, with computation.
5. The demand, and the period allowed for compliance, which must match any statutory
   notice period that applies.
6. The consequence of non compliance, naming the proceedings that will follow.
Closing block: advocate's name, enrolment number, address, and a copy retained clause.

Keep the tone firm and professional. Cite statutory provisions inline.""",
    "Application / Misc. Petition": """Draft an interlocutory application for filing in an Indian court.

Court and case heading.
Title naming the provision, for example "APPLICATION UNDER ORDER XXXIX RULES 1 AND 2 CPC"
or "APPLICATION UNDER SECTION 151 CPC".
Applicant and respondent blocks.
MOST RESPECTFULLY SHOWETH:
1. That the background is as follows.
2. That the applicant seeks the relief stated, on the grounds set out.
3. That there is a prima facie case, giving the specifics.
4. That the balance of convenience lies with the applicant.
5. That irreparable harm will follow if the relief is refused.
6. That the application is made bona fide and not to delay the proceedings.
PRAYER with lettered reliefs, including ex parte ad interim relief where the facts justify it,
and costs.
AFFIDAVIT IN SUPPORT sworn by the applicant or an authorised representative.

Numbering: plain Arabic. Every paragraph opens with "That". Cite the leading authorities on
the relief sought.""",
}


def draft_document(
    doc_type: str,
    facts: str,
    *,
    petitioner: str = "",
    respondent: str = "",
    court: str = "",
    reliefs: str = "",
    extra_instructions: str = "",
    provider: str | None = None,
    model: str | None = None,
) -> str:
    system = _VAKALATNAMA_SYSTEM if doc_type == "Vakalatnama" else _DRAFT_SYSTEM
    instructions = _DOC_INSTRUCTIONS.get(doc_type, "Draft the requested Indian legal document.")

    party_lines = []
    if petitioner:
        party_lines.append(f"PETITIONER OR CLAIMANT: {petitioner}")
    if respondent:
        party_lines.append(f"RESPONDENT OR DEFENDANT: {respondent}")
    if court:
        party_lines.append(f"COURT OR FORUM: {court}")
    party_block = "\n".join(party_lines)

    prompt = f"DOCUMENT TYPE: {doc_type}\n"
    if party_block:
        prompt += party_block + "\n"
    prompt += f"\nFACTS SUPPLIED BY THE LAWYER:\n{clip(facts, 30000)}\n"
    if reliefs:
        prompt += f"\nRELIEFS THE CLIENT WANTS:\n{reliefs}\n"
    prompt += f"\nDRAFTING INSTRUCTIONS:\n{instructions}\n"
    if extra_instructions:
        prompt += f"\nADDITIONAL INSTRUCTIONS FROM THE LAWYER:\n{extra_instructions}\n"

    return llm.generate(
        prompt,
        provider=provider,
        model=model,
        system=system,
        temperature=0.2,
        max_tokens=8000,
    )


_CITE_RE = re.compile(r"\[CITE:\s*([^\]]+)\]")


def extract_citations(text: str) -> list[dict]:
    """Pull every [CITE: ...] marker out of a draft, de duplicated."""
    seen: set[str] = set()
    citations: list[dict] = []
    for match in _CITE_RE.findall(text or ""):
        value = " ".join(match.split()).strip()
        key = value.lower()
        if not value or key in seen:
            continue
        seen.add(key)
        needs_verification = key.startswith("verify")
        display = value
        if needs_verification:
            display = re.sub(r"^verify\s*[-:]?\s*", "", value, flags=re.IGNORECASE).strip()
        kind = "case" if re.search(r"\(\d{4}\)|\bv\.?s?\.?\b", value, re.IGNORECASE) else "statute"
        citations.append(
            {
                "n": len(citations) + 1,
                "citation": display or value,
                "raw": value,
                "needs_verification": needs_verification,
                "kind": "verify" if needs_verification else kind,
            }
        )
    return citations


def strip_citation_markers(text: str) -> str:
    """Produce a clean filing copy where the markers become plain references."""
    def replace(match: re.Match[str]) -> str:
        value = " ".join(match.group(1).split()).strip()
        if value.lower().startswith("verify"):
            cleaned = re.sub(r"^verify\s*[-:]?\s*", "", value, flags=re.IGNORECASE).strip()
            return f"[{cleaned}]" if cleaned else ""
        return f"({value})"

    return _CITE_RE.sub(replace, text or "")


# ---------------------------------------------------------------------------
# Tool 10: Counter Arguments
# ---------------------------------------------------------------------------

_EXTRACT_SYSTEM = """You are a litigation specialist reading the opposing party's pleading.

Extract every material claim, allegation or legal argument it makes. For each one give:
claim_id      a short label such as C1, C2, C3
claim         the assertion in one or two sentences
legal_basis   the statute, contractual clause or doctrine relied on
key_facts     the facts pleaded in support, with dates and figures where given
strength      STRONG, MODERATE or WEAK, judged as an opponent would judge it

Do not merge distinct claims. Do not invent claims that are not pleaded.
Put every claim in one single array. Never stop after the first claim."""

_EXTRACT_SHAPE = """{"items": [
  {"claim_id": "C1", "claim": "", "legal_basis": "", "key_facts": "",
   "strength": "STRONG | MODERATE | WEAK"}
]}"""

_COUNTER_SYSTEM = """You are a senior advocate drafting the response to an opposing claim in
Indian litigation.

For the claim given, produce:
counter_argument  the rebuttal in formal pleading language, ready to drop into a defence
legal_basis       the provisions that defeat or limit the claim, with section numbers
citations         the authorities that support the rebuttal, each with a relevance line
strategy_note     one practical line on how to run this point, for example whether to take
                  it as a preliminary objection or to keep it for final arguments

Use [CITE: source] format inside the counter argument. Mark anything uncertain as
[CITE: verify - what needs checking]. Never invent a case name or a citation."""

_COUNTER_SHAPE = """{
  "counter_argument": "",
  "legal_basis": "",
  "citations": [{"source": "", "relevance": ""}],
  "strategy_note": ""
}"""

_CLAIM_ASK_SYSTEM = """You are senior litigation counsel advising on one specific claim and the
counter argument prepared against it. Give practical, specific advice grounded in Indian law,
naming the provisions and authorities that matter. Say plainly where the position is weak."""


def extract_claims(
    document_text: str, *, provider: str | None = None, model: str | None = None
) -> list[dict]:
    payload = llm.generate_json(
        "Extract every material claim and legal argument from the pleading below. "
        f"Include every one of them.\n\nDOCUMENT:\n{clip(document_text, 60000)}",
        provider=provider,
        model=model,
        system=_EXTRACT_SYSTEM,
        schema_hint=_EXTRACT_SHAPE,
        temperature=0.1,
        max_tokens=6000,
        expect_list=True,
    )

    if isinstance(payload, dict):
        for key in ("claims", "items", "result", "data", "arguments"):
            if isinstance(payload.get(key), list):
                payload = payload[key]
                break
    if not isinstance(payload, list):
        return []

    claims: list[dict] = []
    for index, item in enumerate(payload, start=1):
        if not isinstance(item, dict):
            continue
        strength = str(item.get("strength", "MODERATE")).upper().strip()
        if strength not in ("STRONG", "MODERATE", "WEAK"):
            strength = "MODERATE"
        claims.append(
            {
                "claim_id": str(item.get("claim_id") or f"C{index}").strip(),
                "claim": str(item.get("claim", "")).strip(),
                "legal_basis": str(item.get("legal_basis", "")).strip(),
                "key_facts": str(item.get("key_facts", "")).strip(),
                "strength": strength,
            }
        )
    return [claim for claim in claims if claim["claim"]]


def draft_counter(
    claim: str,
    legal_basis: str = "",
    context: str = "",
    *,
    provider: str | None = None,
    model: str | None = None,
) -> dict:
    prompt = (
        f"CLAIM MADE BY THE OPPOSING PARTY:\n{claim}\n\n"
        f"LEGAL BASIS THEY RELY ON:\n{legal_basis or 'not stated'}\n\n"
        f"FACTS THEY PLEAD:\n{context or 'not stated'}\n\n"
        "Draft the counter argument. Return JSON only."
    )
    payload = llm.generate_json(
        prompt,
        provider=provider,
        model=model,
        system=_COUNTER_SYSTEM,
        schema_hint=_COUNTER_SHAPE,
        temperature=0.2,
        max_tokens=3000,
    )
    if not isinstance(payload, dict):
        payload = {}

    citations: list[dict] = []
    for item in payload.get("citations") or []:
        if isinstance(item, dict):
            citations.append(
                {
                    "source": str(item.get("source", "")).strip(),
                    "relevance": str(item.get("relevance", "")).strip(),
                }
            )
        elif isinstance(item, str) and item.strip():
            citations.append({"source": item.strip(), "relevance": ""})

    return {
        "counter_argument": str(payload.get("counter_argument", "")).strip(),
        "legal_basis": str(payload.get("legal_basis", "")).strip(),
        "citations": citations,
        "strategy_note": str(payload.get("strategy_note", "")).strip(),
    }


def draft_all_counters(
    claims: list[dict], *, provider: str | None = None, model: str | None = None
) -> list[dict]:
    results: list[dict] = []
    for claim in claims:
        counter = draft_counter(
            claim.get("claim", ""),
            claim.get("legal_basis", ""),
            claim.get("key_facts", ""),
            provider=provider,
            model=model,
        )
        results.append(
            {
                "claim_id": claim.get("claim_id", ""),
                "original_claim": claim.get("claim", ""),
                "original_strength": claim.get("strength", ""),
                **counter,
            }
        )
    return results


def assemble_written_statement(
    counters: list[dict],
    *,
    petitioner: str = "",
    respondent: str = "",
    court: str = "",
    extra_defences: str = "",
    provider: str | None = None,
    model: str | None = None,
) -> str:
    prepared = "\n\n".join(
        f"RE CLAIM {counter.get('claim_id', '')} ({counter.get('original_strength', '')}):\n"
        f"Opposing claim: {counter.get('original_claim', '')}\n"
        f"Prepared response: {counter.get('counter_argument', '')}\n"
        f"Legal basis: {counter.get('legal_basis', '')}"
        for counter in counters
    )
    prompt = (
        f"PLAINTIFF OR CLAIMANT: {petitioner or 'as per the plaint'}\n"
        f"DEFENDANT OR RESPONDENT: {respondent or 'the answering defendant'}\n"
        f"COURT OR FORUM: {court or 'as per the cause title'}\n\n"
        f"COUNTER ARGUMENTS ALREADY PREPARED:\n{clip(prepared, 40000)}\n\n"
        f"{'ADDITIONAL DEFENCES TO INCLUDE: ' + extra_defences if extra_defences else ''}\n\n"
        "Assemble these into a single formal Written Statement under Order VIII CPC, with the "
        "cause title, preliminary objections, para wise reply carrying the inline citations, "
        "the defendant's positive case, the prayer, the verification and the annexures list."
    )
    return llm.generate(
        prompt,
        provider=provider,
        model=model,
        system=_DRAFT_SYSTEM,
        temperature=0.25,
        max_tokens=8000,
    )


def ask_about_claim(
    question: str,
    claim: str,
    counter: str = "",
    *,
    provider: str | None = None,
    model: str | None = None,
) -> str:
    counter_block = f"COUNTER ARGUMENT PREPARED:\n{counter}\n\n" if counter else ""
    prompt = (
        f"CLAIM FROM THE OPPOSING PARTY:\n{claim}\n\n"
        f"{counter_block}"
        f"QUESTION FROM THE LAWYER: {question}"
    )
    return llm.generate(
        prompt,
        provider=provider,
        model=model,
        system=_CLAIM_ASK_SYSTEM,
        temperature=0.15,
        max_tokens=3000,
    )
