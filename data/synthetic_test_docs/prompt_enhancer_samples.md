# Prompt Enhancer – Sample Prompts

The **Prompt Enhancer** module (`core.prompt_enhancer`) is designed to take a raw user query and rewrite it into a more precise, context‑rich prompt for the LLM. Below are example inputs and the expected enhanced outputs. Use these samples to test the module or as templates for your own queries.

---

## 1. Basic Legal Research Query

**User Prompt:**
```
Find recent Supreme Court judgments on data privacy in India.
```

**Enhanced Prompt:**
```
Provide a concise summary of Supreme Court of India judgments from 2018 to present that address data privacy, including case name, citation, key holding, and relevance to the Personal Data Protection Bill. List the judgments in chronological order and cite the official reporter.
```

---

## 2. Authority Check Request

**User Prompt:**
```
Check if the case ABC vs XYZ is a good authority for contract breach.
```

**Enhanced Prompt:**
```
Identify whether the case *ABC vs XYZ* (2022) is a binding authority on breach of contract under Indian contract law. Summarize the factual background, legal issue, holding, and explain its relevance to the principle of specific performance versus damages.
```

---

## 3. Translation & OCR Context

**User Prompt:**
```
Translate the attached Hindi document to English and extract dates.
```

**Enhanced Prompt:**
```
Perform OCR on the uploaded Hindi DOCX file, then translate the extracted text to English. Identify all dates in the document, normalise them to ISO‑8601 format (YYYY‑MM‑DD), and present a table with columns: `Original Date`, `Normalized Date`, `Context`. Include the translated surrounding paragraph for each date.
```

---

## 4. Drafting a Legal Notice

**User Prompt:**
```
Help me draft a legal notice for unpaid rent.
```

**Enhanced Prompt:**
```
Draft a formal legal notice addressed to the tenant for non‑payment of rent. Include:
- Parties’ details (landlord and tenant)
- Property address
- Amount overdue and due date
- Reference to the lease agreement clause on rent payment
- Legal consequences of continued default (eviction, interest, recovery costs)
- A deadline for payment (e.g., 15 days from notice date)
- Signature block for the landlord’s counsel.
```

---

## 5. Summarising a Judgment

**User Prompt:**
```
Summarise the judgment in the attached PDF.
```

**Enhanced Prompt:**
```
Read the attached PDF of the judgment, then provide a structured summary containing:
1. Case name and citation
2. Court and date of judgment
3. Facts of the case
4. Legal issues presented
5. Arguments of each party
6. Holding and reasoning
7. Key precedents cited
8. Implications for future cases
Present the summary in bullet points under each heading.
```

---

## How to Use

1. Copy the **User Prompt** into the Streamlit app’s input field.
2. Run the **Prompt Enhancer** feature.
3. Verify that the output matches the **Enhanced Prompt** shown above.

These samples cover a range of typical legal tasks and demonstrate how the enhancer refines vague queries into actionable, detailed prompts for the LLM.
