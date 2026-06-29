"""Tool 6: Legal Document Drafter with Inline Citations.

Drafts Indian litigation documents:
- Suit (Plaint)
- Statement of Claims (Arbitration)
- Written Statement / Statement of Defense
- Rejoinder
- Vakalatnama
- Counter-claim

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

_SYSTEM = """You are a senior advocate at the Supreme Court of India with 20 years of
drafting experience across civil and commercial litigation.

Draft the requested legal document with:
1. Proper Indian court heading format
2. Numbered paragraphs
3. Formal legal language (MOST RESPECTFULLY SHOWETH / WHEREFORE / etc. as appropriate)
4. Inline citations: every factual assertion supported by statute section [CPC s.XX] or
   case law [Case Name, Year Court Citation]
5. A PRAYER / RELIEF section at the end
6. Verification / Affidavit clause where required

Use [CITE: <source>] format for inline citations that can be extracted later.
Do NOT invent case names. Only cite well-known, real Indian statutes and landmark cases.
Mark uncertain citations as [CITE: verify - <description>]."""

_VAKALATNAMA_SYSTEM = """Draft a standard Vakalatnama (Power of Attorney to an Advocate)
in the format used in Indian courts. Include:
- Court name and case details (to be filled)
- Client's authorisation to the named advocate
- List of standard powers granted
- Signature and verification block"""

_DOC_PROMPTS = {
    "Suit (Plaint)": (
        "Draft a formal Plaint (Civil Suit) for filing in an Indian Civil Court. "
        "Include: cause title, jurisdiction clause (CPC s.9 / s.20), "
        "statement of facts in numbered paragraphs, cause of action, "
        "limitation (per Limitation Act 1963), valuation, prayer for relief, "
        "and verification/affidavit."
    ),
    "Statement of Claims": (
        "Draft a Statement of Claims for arbitration proceedings under the Arbitration and "
        "Conciliation Act 1996. Include: background, contractual framework, "
        "claims with legal basis, reliefs claimed, and interest clause."
    ),
    "Written Statement": (
        "Draft a Written Statement (defence) under Order VIII CPC. "
        "Include: preliminary objections, para-wise reply to the plaint, "
        "specific denials, positive case of the defendant, and prayer."
    ),
    "Statement of Defense": (
        "Draft a Statement of Defense for arbitration under the Arbitration and "
        "Conciliation Act 1996. Include: preliminary objections, para-wise reply, "
        "counter-claims (if any), and relief sought."
    ),
    "Rejoinder": (
        "Draft a Rejoinder to the Written Statement / Statement of Defense. "
        "Respond to each preliminary objection and para-wise defence. "
        "Reaffirm the original claims with additional legal arguments."
    ),
    "Vakalatnama": (
        "Draft a standard Vakalatnama (Power of Attorney to Advocate) in standard Indian court format."
    ),
    "Counter-Claim": (
        "Draft a Counter-Claim under Order VIII Rule 6A CPC. "
        "Include: cause of action, legal basis, and prayer for relief."
    ),
    "Application / Misc. Petition": (
        "Draft an interlocutory application / misc. petition for the Indian court. "
        "Include: cause title, grounds, prayer, and affidavit."
    ),
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

    Returns: drafted document text with inline citations.
    """
    doc_prompt = _DOC_PROMPTS.get(doc_type, "Draft the requested legal document.")
    system = _VAKALATNAMA_SYSTEM if doc_type == "Vakalatnama" else _SYSTEM

    party_block = ""
    if petitioner:
        party_block += f"PETITIONER / CLAIMANT: {petitioner}\n"
    if respondent:
        party_block += f"RESPONDENT / DEFENDANT: {respondent}\n"
    if court:
        party_block += f"COURT / FORUM: {court}\n"

    prompt = (
        f"DOCUMENT TYPE: {doc_type}\n"
        f"{party_block}"
        f"\nFACTS PROVIDED BY THE LAWYER:\n{facts}\n\n"
        f"DRAFTING INSTRUCTIONS: {doc_prompt}\n"
    )
    if extra_instructions:
        prompt += f"\nADDITIONAL INSTRUCTIONS: {extra_instructions}\n"

    return gemini_generate(
        prompt,
        system_instruction=system,
        temperature=0.25,
        max_output_tokens=8192,
    )


def extract_citations(drafted_text: str) -> list[dict]:
    """Extract all [CITE: ...] markers from a drafted document."""
    import re
    pattern = r"\[CITE:\s*([^\]]+)\]"
    matches = re.findall(pattern, drafted_text)
    seen = set()
    citations = []
    for i, m in enumerate(matches, 1):
        if m not in seen:
            seen.add(m)
            verify = m.lower().startswith("verify")
            citations.append({
                "n": i,
                "citation": m,
                "needs_verification": verify,
            })
    return citations
