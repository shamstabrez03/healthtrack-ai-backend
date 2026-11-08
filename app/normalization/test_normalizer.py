"""
Test name normalization — maps lab-specific test names to canonical names.
Preserves original names. Context-aware; does not aggressively merge ambiguous tests.
"""

import re
from typing import Optional

# Canonical test name mappings
# Key: lowercase pattern → Value: canonical name
TEST_NAME_MAP = {
    # Liver Function Tests
    "alt": "ALT",
    "sgpt": "ALT",
    "alt (sgpt)": "ALT",
    "alt(sgpt)": "ALT",
    "alanine transaminase": "ALT",
    "alanine aminotransferase": "ALT",
    "s.g.p.t": "ALT",
    "serum glutamic pyruvic transaminase": "ALT",

    "ast": "AST",
    "sgot": "AST",
    "ast (sgot)": "AST",
    "ast(sgot)": "AST",
    "aspartate transaminase": "AST",
    "aspartate aminotransferase": "AST",
    "s.g.o.t": "AST",
    "serum glutamic oxaloacetic transaminase": "AST",

    "alkaline phosphatase": "Alkaline Phosphatase",
    "alp": "Alkaline Phosphatase",
    "alkp": "Alkaline Phosphatase",

    "bilirubin total": "Bilirubin Total",
    "total bilirubin": "Bilirubin Total",
    "serum bilirubin": "Bilirubin Total",
    "bilirubin (total)": "Bilirubin Total",
    "t. bilirubin": "Bilirubin Total",
    "t.bilirubin": "Bilirubin Total",

    "bilirubin direct": "Bilirubin Direct",
    "direct bilirubin": "Bilirubin Direct",
    "conjugated bilirubin": "Bilirubin Direct",
    "d. bilirubin": "Bilirubin Direct",

    "bilirubin indirect": "Bilirubin Indirect",
    "indirect bilirubin": "Bilirubin Indirect",
    "unconjugated bilirubin": "Bilirubin Indirect",

    "ggt": "GGT",
    "gamma gt": "GGT",
    "gamma-gt": "GGT",
    "gamma glutamyl transferase": "GGT",
    "gamma glutamyl transpeptidase": "GGT",
    "ggtp": "GGT",

    "total protein": "Total Protein",
    "serum total protein": "Total Protein",
    "protein total": "Total Protein",

    "albumin": "Albumin",
    "serum albumin": "Albumin",

    "globulin": "Globulin",
    "serum globulin": "Globulin",

    "a/g ratio": "A/G Ratio",
    "a:g ratio": "A/G Ratio",
    "albumin/globulin ratio": "A/G Ratio",
    "albumin globulin ratio": "A/G Ratio",

    # Lipid Profile
    "total cholesterol": "Total Cholesterol",
    "cholesterol total": "Total Cholesterol",
    "serum cholesterol": "Total Cholesterol",
    "cholesterol": "Total Cholesterol",

    "ldl cholesterol": "LDL Cholesterol",
    "ldl": "LDL Cholesterol",
    "ldl-c": "LDL Cholesterol",
    "ldl cholesterol (direct)": "LDL Cholesterol",
    "low density lipoprotein": "LDL Cholesterol",

    "hdl cholesterol": "HDL Cholesterol",
    "hdl": "HDL Cholesterol",
    "hdl-c": "HDL Cholesterol",
    "high density lipoprotein": "HDL Cholesterol",

    "triglycerides": "Triglycerides",
    "triglyceride": "Triglycerides",
    "tg": "Triglycerides",
    "serum triglycerides": "Triglycerides",

    "vldl cholesterol": "VLDL Cholesterol",
    "vldl": "VLDL Cholesterol",
    "vldl-c": "VLDL Cholesterol",

    "total cholesterol/hdl ratio": "TC/HDL Ratio",
    "chol/hdl ratio": "TC/HDL Ratio",
    "cholesterol hdl ratio": "TC/HDL Ratio",

    "ldl/hdl ratio": "LDL/HDL Ratio",
    "ldl hdl ratio": "LDL/HDL Ratio",

    # CBC
    "hemoglobin": "Hemoglobin",
    "haemoglobin": "Hemoglobin",
    "hb": "Hemoglobin",
    "hgb": "Hemoglobin",

    "rbc": "RBC",
    "rbc count": "RBC",
    "red blood cell count": "RBC",
    "total rbc": "RBC",

    "wbc": "WBC",
    "wbc count": "WBC",
    "white blood cell count": "WBC",
    "total wbc": "WBC",
    "total leucocyte count": "WBC",
    "tlc": "WBC",

    "platelet count": "Platelet Count",
    "platelets": "Platelet Count",
    "plt": "Platelet Count",

    "pcv": "PCV",
    "hematocrit": "PCV",
    "hct": "PCV",
    "packed cell volume": "PCV",

    "mcv": "MCV",
    "mean corpuscular volume": "MCV",

    "mch": "MCH",
    "mean corpuscular hemoglobin": "MCH",
    "mean corpuscular haemoglobin": "MCH",

    "mchc": "MCHC",
    "mean corpuscular hemoglobin concentration": "MCHC",

    "rdw": "RDW",
    "rdw-cv": "RDW",
    "red cell distribution width": "RDW",

    "esr": "ESR",
    "erythrocyte sedimentation rate": "ESR",

    # Differential count
    "neutrophils": "Neutrophils",
    "neutrophil": "Neutrophils",
    "lymphocytes": "Lymphocytes",
    "lymphocyte": "Lymphocytes",
    "monocytes": "Monocytes",
    "monocyte": "Monocytes",
    "eosinophils": "Eosinophils",
    "eosinophil": "Eosinophils",
    "basophils": "Basophils",
    "basophil": "Basophils",

    # Thyroid
    "tsh": "TSH",
    "thyroid stimulating hormone": "TSH",
    "ultrasensitive tsh": "TSH",
    "s. tsh": "TSH",

    "t3": "T3",
    "total t3": "T3 Total",
    "free t3": "Free T3",
    "ft3": "Free T3",

    "t4": "T4",
    "total t4": "T4 Total",
    "free t4": "Free T4",
    "ft4": "Free T4",

    # Kidney / Renal
    "creatinine": "Creatinine",
    "serum creatinine": "Creatinine",
    "s. creatinine": "Creatinine",

    "urea": "Urea",
    "blood urea": "Urea",
    "serum urea": "Urea",

    "bun": "BUN",
    "blood urea nitrogen": "BUN",

    "uric acid": "Uric Acid",
    "serum uric acid": "Uric Acid",
    "s. uric acid": "Uric Acid",

    "egfr": "eGFR",
    "estimated gfr": "eGFR",
    "glomerular filtration rate": "eGFR",

    # Diabetes
    "fasting glucose": "Fasting Glucose",
    "fasting blood sugar": "Fasting Glucose",
    "fbs": "Fasting Glucose",
    "glucose fasting": "Fasting Glucose",

    "random glucose": "Random Glucose",
    "random blood sugar": "Random Glucose",
    "rbs": "Random Glucose",

    "hba1c": "HbA1c",
    "glycated hemoglobin": "HbA1c",
    "glycated haemoglobin": "HbA1c",
    "glycosylated hemoglobin": "HbA1c",

    "pp glucose": "PP Glucose",
    "post prandial glucose": "PP Glucose",
    "ppbs": "PP Glucose",

    # Electrolytes
    "sodium": "Sodium",
    "serum sodium": "Sodium",
    "na+": "Sodium",

    "potassium": "Potassium",
    "serum potassium": "Potassium",
    "k+": "Potassium",

    "chloride": "Chloride",
    "serum chloride": "Chloride",
    "cl-": "Chloride",

    "calcium": "Calcium",
    "serum calcium": "Calcium",
    "ca++": "Calcium",

    # Vitamins
    "vitamin d": "Vitamin D",
    "25-oh vitamin d": "Vitamin D",
    "25 hydroxy vitamin d": "Vitamin D",

    "vitamin b12": "Vitamin B12",
    "cyanocobalamin": "Vitamin B12",

    "iron": "Iron",
    "serum iron": "Iron",
    "ferritin": "Ferritin",
    "serum ferritin": "Ferritin",

    # Serology
    "hbsag": "HBsAg",
    "hepatitis b surface antigen": "HBsAg",
    "hbs ag": "HBsAg",

    "hcv": "HCV",
    "anti hcv": "HCV",
    "hepatitis c": "HCV",

    "hiv": "HIV",
    "hiv 1 & 2": "HIV",
    "hiv screening": "HIV",

    # Urine
    "urine ph": "Urine pH",
    "ph (urine)": "Urine pH",
    "specific gravity": "Urine Specific Gravity",
    "urine specific gravity": "Urine Specific Gravity",
    "sp. gravity": "Urine Specific Gravity",
    "urine protein": "Urine Protein",
    "urine glucose": "Urine Glucose",
    "urine ketone": "Urine Ketone",
    "pus cells": "Pus Cells",
    "epithelial cells": "Epithelial Cells",
    "rbc (urine)": "Urine RBC",
    "urine rbc": "Urine RBC",
    "cast": "Urine Cast",
    "urine cast": "Urine Cast",
    "crystals": "Urine Crystals",
    "bacteria": "Urine Bacteria",
}


def normalize_test_name(test_name: str) -> str:
    """
    Map a test name to its canonical form.
    Returns the canonical name, or the original (title-cased) if no mapping found.
    """
    if not test_name:
        return test_name

    # Clean the input
    cleaned = test_name.strip()
    lookup = cleaned.lower()

    # 1. Direct lookup first
    if lookup in TEST_NAME_MAP:
        return TEST_NAME_MAP[lookup]

    # 2. Try with stripped common prefixes/suffixes
    stripped = re.sub(r"^(serum |s\. |blood |plasma )", "", lookup).strip()
    if stripped in TEST_NAME_MAP:
        return TEST_NAME_MAP[stripped]
    if stripped == "bilirubin":
        return "Bilirubin Total"

    # 3. Try without parenthetical content
    no_parens = re.sub(r"\s*\([^)]*\)\s*", "", lookup).strip()
    if no_parens in TEST_NAME_MAP:
        return TEST_NAME_MAP[no_parens]
    no_parens_stripped = re.sub(r"^(serum |s\. |blood |plasma )", "", no_parens).strip()
    if no_parens_stripped in TEST_NAME_MAP:
        return TEST_NAME_MAP[no_parens_stripped]

    # 4. Try the parenthetical content itself
    parens_match = re.search(r"\(([^)]+)\)", lookup)
    if parens_match:
        inner = parens_match.group(1).strip().lower()
        if inner in TEST_NAME_MAP:
            return TEST_NAME_MAP[inner]

    # No mapping found — return original with cleaned formatting
    return cleaned
