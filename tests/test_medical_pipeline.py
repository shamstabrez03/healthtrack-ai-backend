"""Test suite for medical report extraction, normalization, and trend calculation."""

import pytest
from datetime import date
from app.normalization.test_normalizer import normalize_test_name
from app.extraction.validator import determine_status, validate_observation
from app.ingestion.pdf_parser import extract_pdf_text, get_full_text
from pathlib import Path


def test_test_normalization():
    """Verify that lab variations correctly resolve to canonical test names."""
    assert normalize_test_name("ALT (SGPT)") == "ALT"
    assert normalize_test_name("SGPT") == "ALT"
    assert normalize_test_name("Alanine Transaminase") == "ALT"
    assert normalize_test_name("Serum Bilirubin") == "Bilirubin Total"
    assert normalize_test_name("AST (SGOT)") == "AST"
    assert normalize_test_name("SGOT") == "AST"
    assert normalize_test_name("LDL Cholesterol (Direct)") == "LDL Cholesterol"
    assert normalize_test_name("HDL Cholesterol") == "HDL Cholesterol"
    assert normalize_test_name("Triglycerides") == "Triglycerides"
    assert normalize_test_name("TSH") == "TSH"
    assert normalize_test_name("Fasting Blood Sugar") == "Fasting Glucose"
    assert normalize_test_name("Serum Creatinine") == "Creatinine"


def test_status_determination():
    """Verify deterministic reference range status assignment."""
    # Within range
    obs_normal = {
        "value_numeric": 120.0,
        "reference_low": 100.0,
        "reference_high": 150.0,
        "value_type": "numeric"
    }
    assert determine_status(obs_normal) == "within_range"

    # Attention (mildly elevated above reference high)
    obs_attention = {
        "value_numeric": 112.0,
        "reference_low": None,
        "reference_high": 100.0,
        "value_type": "numeric"
    }
    assert determine_status(obs_attention) == "attention"

    # Significant (elevated > 30% above high)
    obs_significant = {
        "value_numeric": 160.0,
        "reference_low": None,
        "reference_high": 100.0,
        "value_type": "numeric"
    }
    assert determine_status(obs_significant) == "significant"

    # Qualitative Negative / Non-reactive
    obs_qual_neg = {
        "value_text": "Non-Reactive",
        "value_type": "qualitative"
    }
    assert determine_status(obs_qual_neg) == "normal"

    # Qualitative Positive
    obs_qual_pos = {
        "value_text": "Positive",
        "value_type": "qualitative"
    }
    assert determine_status(obs_qual_pos) == "attention"


def test_sample_pdf_text_extraction():
    """Verify PyMuPDF extracts text correctly from the sample Blood Test Report.pdf."""
    pdf_path = Path("D:/Gen AI Projects/Medical Report Analyzer/Blood Test Report.pdf")
    if not pdf_path.exists():
        pytest.skip("Sample PDF not found in workspace")

    pages = extract_pdf_text(str(pdf_path))
    assert len(pages) > 0
    full_text = get_full_text(pages)
    assert len(full_text) > 100
    # The sample contains diagnostic laboratory data
    assert any(term in full_text.upper() for term in ["REPORT", "TEST", "LIVER", "LIPID", "CHOLESTEROL", "BILIRUBIN", "RESULT"])
