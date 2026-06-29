# Legal Research Questions for Synthetic Test Docs

This document provides a set of sample legal research questions that can be used to test the **Legal Research** functionality of the `law-project` application. Each question is designed to correspond to one of the synthetic documents generated in this folder.

---

## 1. Civil Suit Sample (`civil_suit_sample.docx`)

**Question:** *What are the procedural steps and timelines for a civil suit filed on 15/01/2024, including service of notice, hearing dates, and judgment?*

**Key Dates to Verify:**
- Filing: 15/01/2024
- Service of Notice: 05/02/2024
- Hearing: 20/03/2024
- Judgment: 10/04/2024

---

## 2. Criminal Case Sample (`criminal_case_sample.pdf`)

**Question:** *Identify the chronology of events in a criminal case, from FIR filing to final judgment, and highlight the statutory periods for investigation and trial.*

**Key Dates to Verify:**
- FIR Date: 12/02/2024
- Arrest: 18/02/2024
- Charge Sheet Filing: 05/03/2024
- First Hearing: 22/03/2024
- Final Judgment: 30/04/2024

---

## 3. Property Dispute Sample (`property_dispute_sample.docx`)

**Question:** *Outline the timeline of a property dispute case, focusing on the agreement, possession, eviction notice, and final decree.*

**Key Dates to Verify:**
- Agreement: 01/07/2023
- Possession: 15/08/2023
- Notice of Eviction: 01/09/2023
- Suit Filing: 20/09/2023
- Interim Order: 10/10/2023
- Final Decree: 05/12/2023

---

## 4. Contract Breach Sample (`contract_breach_sample.pdf`)

**Question:** *Summarize the breach of contract timeline, including contract execution, breach occurrence, notice, suit filing, settlement conference, and judgment.*

**Key Dates to Verify:**
- Contract Execution: 15/03/2022
- Breach: 01/11/2023
- Notice of Breach: 10/11/2023
- Suit Filing: 25/11/2023
- Settlement Conference: 15/12/2023
- Judgment: 20/01/2024

---

## How to Use

1. Upload the corresponding document via the **List of Dates** generator in the Streamlit app.
2. Run the legal‑research module (e.g., `core.legal_research`) with the question above.
3. Verify that the extracted dates and events match the expected timeline.

These questions can also serve as prompts for testing the LLM‑driven research capabilities of the project.
