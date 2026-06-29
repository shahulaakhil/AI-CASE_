# Multilingual Translation & OCR Test Documents

The following synthetic documents have been generated to test the **translation**, **OCR**, and **AI‑driven extraction** pipelines in the `law-project`.

| Language | File | Format | Sample Content |
|----------|------|--------|----------------|
| Hindi | `hindi_sample.docx` | DOCX | A civil‑case excerpt in Hindi with a date (12/01/2024).
| Bengali | `bengali_sample.pdf` | PDF | A criminal‑case excerpt in Bengali with a date (১৫/০২/২০২৪).
| Spanish | `spanish_sample.docx` | DOCX | A civil‑case excerpt in Spanish with a date (20/03/2024).
| French | `french_sample.pdf` | PDF | A criminal‑procedure excerpt in French with a date (05/04/2024).

## How to Use
1. Upload any of the files via the Streamlit **Translation/OCR** interface.
2. The system will:
   - Perform OCR (if PDF or scanned image).
   - Detect the source language.
   - Translate the extracted text to English (or any target language supported by the LLM).
3. Verify that the dates and key legal statements are correctly extracted and translated.

These documents provide a simple yet realistic test set for multilingual legal text handling.
