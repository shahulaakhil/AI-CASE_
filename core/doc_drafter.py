"""Tool 6: Legal Document Drafter with Inline Citations.

Drafts Indian litigation documents:
- Suit (Plaint)
- Statement of Claims (Arbitration)
- Written Statement / Statement of Defense
- Rejoinder
- Vakalatnama
- Counter-claim
- Application / Misc. Petition

Each draft includes inline citations to statutes and case law.
"""
from __future__ import annotations

from .llm import gemini_generate

DOC_TYPES = [
    "Suit (Plaint)",
    "Statement of Claims",
    "Written Statement",
    "Statement of Defense",
    "Rejoinder",
    "Vakalatnama",
    "Counter-Claim",
    "Application / Misc. Petition",
]

_SYSTEM = """You are a senior advocate practising before the Supreme Court of India with
20 years of drafting experience in civil litigation, commercial disputes, and arbitration.

═══════════════════════════════════════════════════════════════════
MANDATORY FORMAT RULES — FOLLOW EXACTLY
═══════════════════════════════════════════════════════════════════

1. PARAGRAPH NUMBERING
   ▸ COURT FILINGS (Plaint, Written Statement, Counter-Claim, Application):
     Plain Arabic numbering — "1.", "2.", "3." — each paragraph beginning with "That…"
   ▸ ARBITRATION DOCUMENTS (Statement of Claims, Statement of Defense, Rejoinder):
     Decimal numbering — "1.1", "1.2", "2.1", "2.2" — under Roman-numeral section headings.

2. SECTION STRUCTURE (arbitration & complex pleadings)
   I.   INTRODUCTION / BACKGROUND
   II.  PRELIMINARY SUBMISSIONS / PRELIMINARY OBJECTIONS
   III. FACTUAL MATRIX
   IV.  LEGAL SUBMISSIONS
        A. [First legal ground — in CAPS or Title Case]
        B. [Second legal ground]
        C. [Third legal ground — add as many as facts warrant]
   V.   RELIEFS SOUGHT

3. DEFINED TERMS
   On first mention, define short-form in parentheses:
     "ABC Pvt. Ltd. (hereinafter 'the Claimant')"
     "Agreement dated 01-01-2024 (hereinafter 'the Agreement')"
   Use the defined term consistently for all subsequent references.

4. ANNEXURE CROSS-REFERENCES
   In the body, mark references in square brackets: [Annexure A], [Annexure B-3]
   At the end of the document include an ANNEXURES section listing each Annexure with
   a one-line description.

5. INLINE CITATIONS — use [CITE: <source>] markers ONLY for:
   ▸ Statutes   → [CITE: CPC s.9], [CITE: A&C Act 1996 s.34], [CITE: ICA s.73]
   ▸ Case law   → [CITE: Case Name (Year) Citation] — ONLY real, well-known cases
   ▸ Uncertain  → [CITE: verify — brief description of case/provision needed]
   NEVER invent citations. Mark ALL uncertain ones as "verify".

6. FORMAL LANGUAGE
   ▸ Court filings: open body with "MOST RESPECTFULLY SHOWETH:"
   ▸ Arbitration:   open body with "RESPECTFULLY SUBMITTED THAT:"
   Use WHEREFORE / PRAYER at the close of the pleadings.

7. CLOSING BLOCK (after PRAYER)
   ▸ VERIFICATION (for court filings) — sworn statement by the party
   ▸ AFFIDAVIT (where required by court rules)
   ▸ Filed through: [Counsel's name], Advocate
     Enrollment No.: ___________
     Date: ___________   Place: ___________

8. DOCUMENT QUALITY
   ▸ Maintain formal, third-person, impersonal legal register throughout.
   ▸ Use tables where comparing quantities, dates, or financial figures.
   ▸ Bold key defined terms and Annexure references for quick scanning.
   ▸ Do NOT add headings or commentary outside the document itself.
═══════════════════════════════════════════════════════════════════"""

_VAKALATNAMA_SYSTEM = """Draft a standard Vakalatnama (Power of Attorney to an Advocate)
in the format used across Indian courts. Include:
- Court name and case number (to be filled)
- Client name, address, and description
- Advocate's name and enrollment number
- Full list of standard powers granted (file, appear, compromise, withdraw, etc.)
- Attestation block: signed before a Notary / Oath Commissioner
- Date and place"""

_DOC_PROMPTS = {
    "Suit (Plaint)": """Draft a formal Plaint (Civil Suit) for filing before an Indian Civil Court.

REQUIRED SECTIONS AND CONTENT:
1. COURT HEADING — "IN THE COURT OF [court name]" with case number placeholder.
2. CAUSE TITLE — Petitioner details (full name, address) vs. Respondent details.
3. PLAINT UNDER [Order VII CPC / relevant provision]:
   - Para 1: Parties — who the Plaintiff is, occupation, address.
   - Para 2: Jurisdiction — territorial [CITE: CPC s.20], pecuniary, and subject-matter.
   - Para 3 onwards: Chronological facts with dates, amounts, and references to
     documents ([Annexure A], [Annexure B], etc.).
   - Second-last para: Limitation — date of cause of action, period under
     [CITE: Limitation Act 1963, relevant Article].
   - Last para: Valuation of suit and court-fee paid.
4. PRAYER — numbered sub-clauses a), b), c) for each relief sought, including interest
   and costs.
5. VERIFICATION — sworn para-wise verification by the Plaintiff.
6. ANNEXURES — list of documents filed with the Plaint.

Style: Plain Arabic paragraph numbering (1., 2., 3.); each para starting "That…"
Inline citations for every jurisdictional and limitation claim.""",

    "Statement of Claims": """Draft a Statement of Claims for arbitration proceedings under the
Arbitration and Conciliation Act 1996.

REQUIRED SECTIONS:
I. INTRODUCTION
   1.1 Parties — Claimant and Respondent (with defined terms).
   1.2 Arbitration agreement and appointment of Arbitrator.
   1.3 Overview of dispute in 2–3 sentences.

II. FACTUAL BACKGROUND
   2.1 – 2.N Chronological facts. Reference each supporting document as [Annexure C-N].
   Use a table if comparing deliveries, payments, or timelines.

III. LEGAL FRAMEWORK
   3.1 Governing law and jurisdiction [CITE: A&C Act 1996 s.7, s.11 as applicable].
   3.2 Applicable substantive law [CITE: ICA 1872 ss. relevant].

IV. CLAIMS
   A. CLAIM I — [Heading describing first breach/cause]
      4.1 – 4.N Factual and legal basis; quantum computation.
   B. CLAIM II — [Second claim if any]
   C. CLAIM III — [Third claim if any]
   Add sub-headings A, B, C for each distinct claim head.

V. RELIEF CLAIMED
   The Claimant respectfully submits that this Hon'ble Tribunal may:
   a) Award Rs. [amount] as principal damages [CITE: ICA s.73].
   b) Award interest @ [rate]% p.a. from [date] [CITE: A&C Act 1996 s.31(7)].
   c) Award costs of arbitration.
   d) Pass any other relief deemed just and equitable.

VERIFICATION
ANNEXURES — list all documents with C-N numbering.

Style: Decimal paragraph numbering (1.1, 1.2 etc.); professional arbitration register.""",

    "Written Statement": """Draft a Written Statement (defence) under Order VIII CPC for filing
before an Indian Civil Court.

REQUIRED SECTIONS:
PRELIMINARY OBJECTIONS (numbered I, II, III):
- Objection I: Maintainability / jurisdiction if applicable [CITE: CPC s.XX].
- Objection II: Limitation [CITE: Limitation Act 1963].
- Objection III: Non-joinder / mis-joinder, if relevant.

PARA-WISE REPLY:
For each para of the Plaint draft a corresponding reply paragraph:
  "Re Para 1: The contents of Para 1 are [admitted / denied] to the extent that…"
Follow with positive averments where the Defendant's version differs.

DEFENDANT'S POSITIVE CASE:
A. [First substantive defence — e.g., accord and satisfaction]
   Para X: That…
B. [Second defence — e.g., estoppel or waiver]

COUNTER-CLAIM (if any):
Drafted under Order VIII Rule 6A CPC with its own prayer.

PRAYER:
"It is therefore most respectfully prayed that this Hon'ble Court be pleased to dismiss
the suit with costs."

VERIFICATION.
ANNEXURES — exhibits filed with the Written Statement (Annexure D-N series).

Style: Plain Arabic paragraph numbering; each para starting "That…"
Inline citations for every legal proposition invoked.""",

    "Statement of Defense": """Draft a Statement of Defense for arbitration under the
Arbitration and Conciliation Act 1996.

REQUIRED SECTIONS:
I. INTRODUCTION
   1.1 Brief description of the parties and arbitration.
   1.2 Respondent's overall position in one paragraph.

II. PRELIMINARY OBJECTIONS
   A. Jurisdiction / maintainability of claims [CITE: A&C Act 1996 s.16].
   B. Limitation [CITE: Limitation Act 1963].
   C. Any other threshold objection.

III. RESPONSE TO CLAIMANT'S FACTUAL BACKGROUND
   3.1 – 3.N Para-wise response to each factual assertion in the Statement of Claims.
   Format: "In response to para [X] of the SoC, the Respondent states that…"
   Reference defence documents as [Annexure R-N].

IV. RESPONDENT'S POSITIVE CASE
   A. [First substantive defence — e.g., force majeure, impossibility of performance]
      4.1 – 4.N factual and legal basis.
   B. [Second defence]
   Counter-claim if warranted — with separate quantum.

V. RELIEF SOUGHT
   a) Dismiss all claims of the Claimant.
   b) [Counter-claim relief if any.]
   c) Award costs of arbitration to the Respondent.

VERIFICATION.
ANNEXURES — Annexure R-N series for Respondent's documents.

Style: Decimal paragraph numbering; arbitration register.""",

    "Rejoinder": """Draft a Rejoinder to the Written Statement / Statement of Defense.
This is a rebuttal document — respond sharply to each submission of the opposite party
and re-affirm the original claims with stronger legal authority.

REQUIRED SECTIONS:
I. INTRODUCTION
   1.1 Identify the pleading being responded to (Written Statement / SoD dated [date]).
   1.2 State that the denials and positive case in the WS/SoD are denied save where
       expressly admitted below.

II. REPLY TO PRELIMINARY OBJECTIONS
   A. Re Preliminary Objection I — [heading] (state and rebut concisely)
      2.1 – 2.N legal basis for overruling the objection [CITE: relevant case/statute].
   B. Re Preliminary Objection II — [heading]

III. PARA-WISE REPLY TO WRITTEN STATEMENT / STATEMENT OF DEFENSE
   3.1 Re Para 1 of WS/SoD: [Admit / deny / clarify]
   3.2 Re Para 2 of WS/SoD: [Admit / deny / clarify]
   …continue for each paragraph, adding legal argument where useful.
   Reference new evidence as [Annexure C-N] (claimant/plaintiff series).

IV. LEGAL SUBMISSIONS IN REJOINDER
   A. [First legal ground reinforcing the original claim — e.g., breach is proven]
      4.1 – 4.N with case law citations.
   B. [Second ground — e.g., quantum is established by documents]
   C. [Counter the opponent's specific legal defence]

V. PRAYER
   In view of the above, it is most respectfully prayed that this Hon'ble
   Tribunal / Court may be pleased to:
   a) Reject the preliminary objections of the Respondent / Defendant.
   b) Affirm the reliefs prayed for in the Statement of Claims / Plaint.
   c) Pass any other order as deemed just and equitable.

VERIFICATION.
ANNEXURES — new documents filed with the Rejoinder.

Style: Decimal paragraph numbering (1.1, 1.2); bold defined terms;
bold Annexure cross-references; professional arbitration register.""",

    "Vakalatnama": (
        "Draft a standard Vakalatnama (Power of Attorney to Advocate) in standard Indian "
        "court format. The document must include: court name and case details (to be filled), "
        "client's name and address, advocate's name and enrollment number, full standard powers "
        "(file, plead, appear, compromise, withdraw, appeal, execute decrees), attestation block "
        "before Notary/Oath Commissioner, and signature/date/place blocks."
    ),

    "Counter-Claim": """Draft a Counter-Claim under Order VIII Rule 6A CPC for filing
along with the Written Statement.

STRUCTURE:
CAUSE TITLE (same as main suit but Defendant as Counter-Claimant).

COUNTER-CLAIM UNDER ORDER VIII RULE 6A CPC:
1. That the Defendant / Counter-Claimant is the same party who has filed the Written
   Statement in the above-captioned suit. [CITE: CPC Order VIII Rule 6A]
2. That in addition to the defence taken in the Written Statement, the Defendant has an
   independent cause of action against the Plaintiff arising from [facts].
3 onwards: State facts of the counter-claim in numbered paras ("That…").
N–1: Limitation and jurisdiction for counter-claim.
N: Relief(s) sought by the counter-claimant.

PRAYER:
"It is most respectfully prayed that this Hon'ble Court may be pleased to:
a) [First counter-claim relief]
b) [Award interest]
c) [Costs]"

VERIFICATION.
ANNEXURES — exhibits in D-N series.

Style: Plain Arabic numbering; each para starting "That…"
Clearly distinguish counter-claim facts from the Written Statement.""",

    "Application / Misc. Petition": """Draft an interlocutory application / miscellaneous
petition for filing before an Indian court.

STRUCTURE:
IN THE [COURT], [CASE DETAILS]

APPLICATION UNDER [specific provision — e.g., Order XXXIX Rules 1&2 CPC / s.151 CPC]

APPLICANT / PETITIONER: [Party name]
RESPONDENT / OPPOSITE PARTY: [Party name]

MOST RESPECTFULLY SHOWETH:
1. That [brief background — 1–2 paras].
2. That the Applicant requires [the relief] because [grounds].
3. That [facts supporting urgency / irreparable harm].
4. That without the relief, the Applicant will suffer [irreparable loss].
5. That the balance of convenience lies in favour of the Applicant.
6. That this application is made bona fide.

PRAYER:
"It is most respectfully prayed that this Hon'ble Court may be pleased to:
a) [Specific interim / misc. relief]
b) [Ex-parte ad-interim relief if urgent]
c) Costs."

AFFIDAVIT IN SUPPORT:
Standard affidavit sworn by the Applicant or their authorised representative.

Style: Plain Arabic numbering; each para starting "That…"
Include strong case-law citations for the relief sought [CITE: landmark cases on
injunction / stay / condonation / as applicable].""",
}


def draft_document(
    doc_type: str,
    facts: str,
    petitioner: str = "",
    respondent: str = "",
    court: str = "",
    extra_instructions: str = "",
) -> str:
    """Draft a legal document.

    Returns: drafted document text with inline [CITE: …] markers.
    """
    doc_prompt = _DOC_PROMPTS.get(doc_type, "Draft the requested legal document.")
    system = _VAKALATNAMA_SYSTEM if doc_type == "Vakalatnama" else _SYSTEM

    party_block = ""
    if petitioner:
        party_block += f"PETITIONER / CLAIMANT: {petitioner}\n"
    if respondent:
        party_block += f"RESPONDENT / DEFENDANT:  {respondent}\n"
    if court:
        party_block += f"COURT / FORUM:           {court}\n"

    prompt = (
        f"DOCUMENT TYPE: {doc_type}\n"
        f"{party_block}"
        f"\nFACTS PROVIDED BY THE LAWYER:\n{facts}\n\n"
        f"DRAFTING INSTRUCTIONS:\n{doc_prompt}\n"
    )
    if extra_instructions:
        prompt += f"\nADDITIONAL INSTRUCTIONS: {extra_instructions}\n"

    return gemini_generate(
        prompt,
        system_instruction=system,
        temperature=0.2,
        max_output_tokens=8192,
    )


def extract_citations(drafted_text: str) -> list[dict]:
    """Extract all [CITE: …] markers from a drafted document."""
    import re
    pattern = r"\[CITE:\s*([^\]]+)\]"
    matches = re.findall(pattern, drafted_text)
    seen: set[str] = set()
    citations: list[dict] = []
    for i, m in enumerate(matches, 1):
        m = m.strip()
        if m not in seen:
            seen.add(m)
            verify = m.lower().startswith("verify")
            citations.append({
                "n": i,
                "citation": m,
                "needs_verification": verify,
            })
    return citations
