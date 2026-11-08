"""
Report metadata and observation extraction using Gemini.

Extracts patient info, dates, report metadata, and all test observations
from multi-page medical reports using structured prompting.
"""

import json
import re
from typing import List, Dict, Optional, Any
from app.ingestion.pdf_parser import PageContent


EXTRACTION_PROMPT = """You are a medical report data extraction specialist. Extract ALL structured information from this medical report text.

IMPORTANT RULES:
1. Extract EVERY test/observation found in the report
2. Preserve original values exactly as written
3. Do NOT invent or guess values not in the report
4. Handle multi-page reports — information may repeat across pages (same patient/report metadata)
5. Distinguish between specimen collection date, report generated date, and report date
6. For each test, record which page it was found on
7. Parse reference ranges carefully: "<100", ">40", "0.3-1.2", "Up to 41" etc.
8. Handle qualitative results: Positive/Negative, Reactive/Non-Reactive, Trace, etc.

Extract the following JSON structure:

{{
  "patient": {{
    "name": "patient name or null",
    "age": "age as string or null",
    "gender": "M/F/Male/Female or null",
    "patient_id": "any patient ID/lab number or null",
    "referring_doctor": "referring doctor name or null"
  }},
  "report": {{
    "report_type": "blood_test|xray|ultrasound|ecg|urine_test|thyroid|lipid_profile|liver_function|kidney_function|cbc|other",
    "laboratory": "lab/hospital name or null",
    "lab_number": "lab report number or null",
    "collection_date": "YYYY-MM-DD or null",
    "collection_time": "HH:MM or null",
    "reported_date": "YYYY-MM-DD or null",
    "generated_date": "YYYY-MM-DD or null",
    "report_date": "YYYY-MM-DD - best clinical date (prefer collection_date > reported_date > generated_date)"
  }},
  "observations": [
    {{
      "panel": "panel/category name (e.g., Lipid Profile, Liver Function Test, CBC, Thyroid)",
      "test_name": "exact test name as written on report",
      "value_text": "exact value as written (e.g., '112.16', 'Non-Reactive', 'Negative', '1.025')",
      "value_numeric": 112.16 or null if non-numeric,
      "value_type": "numeric|text|qualitative",
      "unit": "unit as written or null",
      "reference_text": "reference range exactly as written (e.g., '<100', '0.3-1.2', 'Up to 41')",
      "reference_low": null or number,
      "reference_high": null or number,
      "interpretation": "any interpretation/notes from the report for this test, or null",
      "source_page": 1,
      "source_text": "the exact line or lines from the report containing this result",
      "confidence": 0.95
    }}
  ]
}}

MEDICAL REPORT TEXT:
{report_text}

Respond with ONLY the JSON object, no other text."""


def extract_report_data(pages: List[PageContent], api_key: str, model_name: str = "gemini-2.5-flash") -> Dict[str, Any]:
    """
    Extract structured data from medical report pages using Gemini.
    
    Args:
        pages: List of PageContent objects from PDF extraction
        api_key: Gemini API key
        model_name: Gemini model to use
    
    Returns:
        Parsed JSON with patient, report, and observations data
    """
    import google.generativeai as genai

    # Combine all pages with page markers
    full_text = ""
    for page in pages:
        if page.text.strip():
            full_text += f"\n--- PAGE {page.page_number} ---\n{page.text}\n"

    if not full_text.strip():
        raise ValueError("No text content found in the document")

    prompt = EXTRACTION_PROMPT.format(report_text=full_text)

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(model_name)

    response = model.generate_content(
        prompt,
        generation_config=genai.GenerationConfig(
            temperature=0.1,
            response_mime_type="application/json",
        ),
    )

    # Parse the JSON response
    response_text = response.text.strip()

    # Clean up potential markdown code blocks
    if response_text.startswith("```"):
        response_text = re.sub(r"^```(?:json)?\s*", "", response_text)
        response_text = re.sub(r"\s*```$", "", response_text)

    try:
        data = json.loads(response_text)
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to parse extraction response as JSON: {e}\nResponse: {response_text[:500]}")

    return data


def classify_report_type(full_text: str, api_key: str, model_name: str = "gemini-2.5-flash") -> str:
    """Classify the type of medical report from its text."""
    import google.generativeai as genai

    prompt = f"""Classify this medical report into ONE of these categories:
- blood_test (includes CBC, blood chemistry, complete blood count)
- liver_function (LFT, liver panel)
- lipid_profile (cholesterol, triglycerides)
- kidney_function (renal function, KFT)
- thyroid (TSH, T3, T4)
- diabetes (glucose, HbA1c)
- urine_test (urine examination, urinalysis)
- xray (X-ray report)
- ultrasound (ultrasound/sonography report)
- ecg (ECG/EKG report)
- cbc (complete blood count only)
- vitamin_mineral (vitamin D, B12, iron studies)
- other

If the report contains MULTIPLE panels (e.g., LFT + Lipid + Thyroid in one report), classify as "blood_test".

Respond with ONLY the category name, nothing else.

Report text (first 2000 chars):
{full_text[:2000]}"""

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(model_name)
    response = model.generate_content(prompt, generation_config=genai.GenerationConfig(temperature=0))
    return response.text.strip().lower()
