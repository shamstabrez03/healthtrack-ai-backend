"""Validation for extracted medical observations."""

import re
from typing import Dict, Any, Optional, List
from app.config import settings


# Biologically implausible ranges for common tests — used for sanity checking
PLAUSIBLE_RANGES = {
    "hemoglobin": (1, 25),
    "rbc": (0.5, 10),
    "wbc": (500, 200000),
    "platelet": (5000, 2000000),
    "total cholesterol": (50, 600),
    "ldl cholesterol": (10, 500),
    "hdl cholesterol": (5, 150),
    "triglycerides": (10, 2000),
    "glucose": (10, 1000),
    "fasting glucose": (10, 1000),
    "creatinine": (0.1, 30),
    "urea": (1, 300),
    "bilirubin total": (0, 50),
    "alt": (1, 5000),
    "ast": (1, 5000),
    "tsh": (0.001, 200),
    "hba1c": (2, 20),
    "uric acid": (0.5, 25),
    "sodium": (100, 200),
    "potassium": (1, 10),
    "calcium": (3, 20),
}


def validate_observation(obs: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate a single observation and set confidence + needs_review flags.
    Does NOT modify the original values — only adds validation metadata.
    """
    confidence = obs.get("confidence", 0.9)
    needs_review = False
    issues = []

    # 1. Must have a test name
    if not obs.get("test_name"):
        confidence = 0.0
        needs_review = True
        issues.append("Missing test name")
        obs["confidence"] = confidence
        obs["needs_review"] = needs_review
        return obs

    # 2. Validate numeric values
    if obs.get("value_type") == "numeric" and obs.get("value_numeric") is not None:
        value = obs["value_numeric"]

        # Check for biologically implausible values
        test_lower = obs.get("test_name", "").lower()
        for test_key, (low, high) in PLAUSIBLE_RANGES.items():
            if test_key in test_lower:
                if value < low or value > high:
                    confidence = min(confidence, 0.3)
                    needs_review = True
                    issues.append(f"Value {value} outside plausible range ({low}-{high})")
                break

    # 3. Validate reference range consistency
    ref_low = obs.get("reference_low")
    ref_high = obs.get("reference_high")
    if ref_low is not None and ref_high is not None:
        if ref_low > ref_high:
            confidence = min(confidence, 0.5)
            needs_review = True
            issues.append(f"Reference low ({ref_low}) > high ({ref_high})")

    # 4. Check value_text exists
    if not obs.get("value_text"):
        confidence = min(confidence, 0.5)
        needs_review = True
        issues.append("Missing value text")

    # 5. Apply confidence threshold
    if confidence < settings.CONFIDENCE_THRESHOLD:
        needs_review = True

    obs["confidence"] = round(confidence, 2)
    obs["needs_review"] = needs_review
    if issues:
        existing_notes = obs.get("notes") or ""
        obs["notes"] = (existing_notes + " | Validation: " + "; ".join(issues)).strip(" | ")

    return obs


def validate_observations(observations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Validate a list of observations."""
    return [validate_observation(obs) for obs in observations]


def determine_status(obs: Dict[str, Any]) -> str:
    """
    Determine the observation status based on reference ranges.
    Uses deterministic logic — NOT the LLM.
    """
    value = obs.get("value_numeric")
    ref_low = obs.get("reference_low")
    ref_high = obs.get("reference_high")
    value_text = (obs.get("value_text") or "").strip().lower()

    # Handle qualitative results
    if obs.get("value_type") == "qualitative":
        positive_terms = {"positive", "reactive", "detected", "present", "abnormal"}
        negative_terms = {"negative", "non-reactive", "non reactive", "not detected", "absent", "normal", "nil"}

        if any(term in value_text for term in negative_terms):
            return "normal"
        if any(term in value_text for term in positive_terms):
            return "attention"
        return "unknown"

    # Handle numeric results
    if value is None:
        return "unknown"

    if ref_low is not None and ref_high is not None:
        if ref_low <= value <= ref_high:
            return "within_range"
        elif value < ref_low:
            deviation = abs(value - ref_low) / abs(ref_low) if ref_low != 0 else 0
            return "significant" if deviation > 0.3 else "attention"
        else:
            deviation = abs(value - ref_high) / abs(ref_high) if ref_high != 0 else 0
            return "significant" if deviation > 0.3 else "attention"

    if ref_high is not None:
        if value <= ref_high:
            return "within_range"
        deviation = abs(value - ref_high) / abs(ref_high) if ref_high != 0 else 0
        return "significant" if deviation > 0.3 else "attention"

    if ref_low is not None:
        if value >= ref_low:
            return "within_range"
        deviation = abs(value - ref_low) / abs(ref_low) if ref_low != 0 else 0
        return "significant" if deviation > 0.3 else "attention"

    return "unknown"
