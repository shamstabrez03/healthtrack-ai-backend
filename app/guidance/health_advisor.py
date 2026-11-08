"""
Health Guidance and Urgent Doctor Alert Engine.

Provides:
1. Urgent medical attention alerts for serious/critical laboratory abnormalities.
2. Personalized report-based health suggestions (Diet, Exercise, Lifestyle, Do's & Don'ts).
3. Grounded educational framing strictly without prescribing or changing medications.
"""

import json
import logging
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from app.database.models import Observation, Report, ObservationStatus
from app.database.repositories import ObservationRepository, ReportRepository, UserRepository
from app.schemas.guidance import HealthGuidance, UrgentAlert, UrgentAlertItem
from app.api.auth import decrypt_api_key

logger = logging.getLogger(__name__)

# Critical thresholds that trigger urgent doctor evaluation alerts
CRITICAL_THRESHOLDS = {
    "ALT": {"high_multiplier": 3.0, "reason": "Significantly elevated liver transaminase (ALT) may indicate acute liver inflammation or injury."},
    "AST": {"high_multiplier": 3.0, "reason": "Significantly elevated AST transaminase suggests notable hepatic or muscular tissue strain."},
    "Bilirubin Total": {"high_multiplier": 2.5, "reason": "Markedly elevated total bilirubin can be associated with acute biliary obstruction or hemolysis."},
    "Fasting Glucose": {"absolute_high": 250.0, "absolute_low": 55.0, "reason": "Marked blood glucose deviation requiring prompt glycemic assessment."},
    "HbA1c": {"absolute_high": 10.5, "reason": "Severely elevated glycated hemoglobin indicating prolonged severe hyperglycemia."},
    "Creatinine": {"absolute_high": 2.5, "reason": "Significantly elevated serum creatinine may signal acute or progressive renal impairment."},
    "Potassium": {"absolute_high": 6.0, "absolute_low": 3.0, "reason": "Critical electrolyte imbalance that requires urgent medical verification."},
    "Hemoglobin": {"absolute_low": 7.5, "reason": "Severe anemia requiring urgent diagnostic evaluation and clinical intervention."},
    "Platelet Count": {"absolute_low": 40000, "reason": "Marked thrombocytopenia with potential risk of bleeding."},
    "WBC": {"absolute_high": 25000, "absolute_low": 2000, "reason": "Severe leukocytosis or leukopenia warranting prompt medical review."},
    "TSH": {"absolute_high": 15.0, "absolute_low": 0.05, "reason": "Substantial thyroid axis dysfunction."},
    "Uric Acid": {"absolute_high": 10.0, "reason": "Markedly elevated uric acid predisposing to acute gout flare or renal calculi."},
}


def analyze_report_guidance(
    db: Session,
    patient_id: str,
    user_id: str,
    report_id: Optional[str] = None,
) -> HealthGuidance:
    """
    Generate comprehensive health guidance and urgent alerts for a report.
    If report_id is not specified, uses the patient's latest completed report.
    """
    # 1. Fetch target report
    if report_id:
        report = ReportRepository.get_by_id(db, report_id, patient_id)
    else:
        latest = ReportRepository.get_latest_reports(db, patient_id, limit=1)
        report = latest[0] if latest else None

    if not report:
        return HealthGuidance(
            general_summary="No medical reports available yet. Upload a report to receive personalized health guidance.",
            dos=["Upload your diagnostic reports to track longitudinal health trends."],
            donts=["Do not rely on unverified self-treatment without professional medical evaluation."],
            diet_suggestions=["Maintain a balanced whole-food diet rich in vegetables and hydration."],
            lifestyle_suggestions=["Aim for regular moderate exercise and 7-8 hours of sleep."],
            doctor_questions=["What baseline health screenings are recommended for my age and lifestyle?"],
        )

    # 2. Fetch observations for this report
    observations = ObservationRepository.get_for_report(db, report.id, patient_id)

    # 3. Deterministic Urgent Findings Detection
    urgent_items: List[UrgentAlertItem] = []
    attention_tests: List[Dict[str, Any]] = []

    for obs in observations:
        test_canonical = obs.canonical_test_name or obs.test_name
        val_num = obs.value_numeric
        val_text = (obs.value_text or "").strip()
        ref_low = obs.reference_low
        ref_high = obs.reference_high
        ref_text = obs.reference_text or (f"{ref_low} - {ref_high}" if ref_low is not None and ref_high is not None else None)

        is_urgent = False
        urgency_reason = ""

        # Check qualitative alerts (e.g. positive viral markers)
        if obs.value_type == "qualitative":
            pos_triggers = ["positive", "reactive", "detected"]
            if any(t in val_text.lower() for t in pos_triggers):
                is_urgent = True
                urgency_reason = f"Reactive or positive result detected on {obs.test_name}, requiring physician consultation."

        # Check deterministic critical thresholds
        if val_num is not None:
            rule = CRITICAL_THRESHOLDS.get(test_canonical)
            if rule:
                if "high_multiplier" in rule and ref_high and val_num >= (ref_high * rule["high_multiplier"]):
                    is_urgent = True
                    urgency_reason = rule["reason"]
                elif "absolute_high" in rule and val_num >= rule["absolute_high"]:
                    is_urgent = True
                    urgency_reason = rule["reason"]
                elif "absolute_low" in rule and val_num <= rule["absolute_low"]:
                    is_urgent = True
                    urgency_reason = rule["reason"]

        if obs.status == ObservationStatus.POTENTIALLY_URGENT.value:
            is_urgent = True
            if not urgency_reason:
                urgency_reason = f"Observation {obs.test_name} marked as needing prompt medical attention."

        if is_urgent:
            urgent_items.append(UrgentAlertItem(
                test_name=obs.test_name,
                observed_value=f"{obs.value_text or obs.value_numeric} {obs.unit or ''}".strip(),
                reference_interval=ref_text,
                reason=urgency_reason,
                severity="urgent"
            ))

        if obs.status in [ObservationStatus.ATTENTION.value, ObservationStatus.SIGNIFICANT.value, ObservationStatus.POTENTIALLY_URGENT.value]:
            attention_tests.append({
                "name": obs.test_name,
                "canonical": test_canonical,
                "value": f"{obs.value_text or obs.value_numeric} {obs.unit or ''}".strip(),
                "reference": ref_text,
                "status": obs.status,
            })

    urgent_alert = None
    if urgent_items:
        urgent_alert = UrgentAlert(
            has_urgent_findings=True,
            title="Urgent Medical Attention Recommended",
            summary=f"We detected {len(urgent_items)} significantly abnormal finding{'s' if len(urgent_items) > 1 else ''} in this report that may require prompt medical evaluation.",
            alert_items=urgent_items,
            recommendation="Please share this report with your physician or healthcare specialist promptly for an in-person medical evaluation. Do not start, discontinue, or adjust any medications without a doctor's direction.",
        )

    # 4. Try Gemini-enhanced guidance if user has configured API key
    user = UserRepository.get_by_id(db, user_id)
    api_key = decrypt_api_key(user.gemini_api_key_encrypted) if user and user.gemini_api_key_encrypted else None

    if api_key:
        try:
            ai_guidance = _generate_ai_guidance(
                api_key=api_key,
                model_name=user.gemini_model or "gemini-2.5-flash",
                report=report,
                observations=observations,
                attention_tests=attention_tests,
                urgent_alert=urgent_alert,
            )
            if ai_guidance:
                return ai_guidance
        except Exception as e:
            logger.warning(f"AI guidance generation failed, falling back to rule engine: {e}")

    # 5. Deterministic Rule-Based Guidance fallback
    return _generate_rule_based_guidance(report, observations, attention_tests, urgent_alert)


def _generate_ai_guidance(
    api_key: str,
    model_name: str,
    report: Report,
    observations: List[Observation],
    attention_tests: List[Dict[str, Any]],
    urgent_alert: Optional[UrgentAlert],
) -> Optional[HealthGuidance]:
    """Generate structured educational guidance via Gemini."""
    import google.generativeai as genai

    obs_summary = []
    for obs in observations:
        flag = f" [{obs.status}]" if obs.status and obs.status != "unknown" else ""
        obs_summary.append(f"- {obs.test_name}: {obs.value_text or obs.value_numeric} {obs.unit or ''} (Ref: {obs.reference_text or 'N/A'}){flag}")

    prompt = f"""You are a preventive health educator for HealthTrack AI.
Analyze the following laboratory report findings and provide practical, educational, non-diagnostic guidance.

CRITICAL RULES:
1. You are NOT a doctor. Do NOT diagnose medical conditions.
2. Do NOT prescribe, recommend, or alter any medications or drug dosages.
3. Clearly separate general lifestyle/dietary habits from professional medical advice.
4. Base recommendations strictly on the observed laboratory results.
5. Provide actionable, realistic Do's and Don'ts tailored to the test findings (e.g. cholesterol, liver enzymes, blood count, glucose, uric acid).

REPORT DETAILS:
Type: {report.report_type or 'Medical Report'}
Clinical Date: {report.report_date or report.upload_timestamp}

OBSERVATIONS:
{chr(10).join(obs_summary[:60])}

Return a valid JSON object matching EXACTLY this structure:
{{
  "general_summary": "A 2-3 sentence clear educational overview of the report findings.",
  "dos": [
    "Concrete positive action item (e.g. Increase soluble fiber intake...)",
    "Concrete positive action item...",
    "Concrete positive action item...",
    "Concrete positive action item..."
  ],
  "donts": [
    "Concrete habit to avoid (e.g. Avoid excessive saturated/trans fats...)",
    "Concrete habit to avoid...",
    "Concrete habit to avoid...",
    "Concrete habit to avoid..."
  ],
  "diet_suggestions": [
    "Dietary recommendation tailored to findings...",
    "Dietary recommendation tailored to findings...",
    "Dietary recommendation tailored to findings..."
  ],
  "lifestyle_suggestions": [
    "Exercise or lifestyle habit tailored to findings...",
    "Sleep, hydration, or stress habit tailored to findings...",
    "Monitoring habit..."
  ],
  "doctor_questions": [
    "Specific question to ask the physician during the next consultation...",
    "Specific question to ask the physician...",
    "Specific question to ask the physician..."
  ]
}}

Respond with ONLY the JSON object."""

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(model_name)

    response = model.generate_content(
        prompt,
        generation_config=genai.GenerationConfig(
            temperature=0.2,
            response_mime_type="application/json",
        ),
    )

    text = response.text.strip()
    data = json.loads(text)

    return HealthGuidance(
        report_id=report.id,
        report_type=report.report_type,
        report_date=str(report.report_date or report.upload_timestamp).split(" ")[0],
        urgent_alert=urgent_alert,
        general_summary=data.get("general_summary", "Report analyzed successfully."),
        dos=data.get("dos", []),
        donts=data.get("donts", []),
        diet_suggestions=data.get("diet_suggestions", []),
        lifestyle_suggestions=data.get("lifestyle_suggestions", []),
        doctor_questions=data.get("doctor_questions", []),
    )


def _generate_rule_based_guidance(
    report: Report,
    observations: List[Observation],
    attention_tests: List[Dict[str, Any]],
    urgent_alert: Optional[UrgentAlert],
) -> HealthGuidance:
    """Generate structured educational suggestions via deterministic clinical rules."""
    dos = []
    donts = []
    diet = []
    lifestyle = []
    questions = []

    has_lipid = any("cholesterol" in t["name"].lower() or "triglyceride" in t["name"].lower() for t in attention_tests)
    has_liver = any(k in t["canonical"].upper() for t in attention_tests for k in ["ALT", "AST", "BILIRUBIN", "GGT", "SGPT", "SGOT"])
    has_sugar = any("glucose" in t["name"].lower() or "hba1c" in t["name"].lower() for t in attention_tests)
    has_uric = any("uric" in t["name"].lower() for t in attention_tests)
    has_hemoglobin = any("hemoglobin" in t["name"].lower() or "hb" in t["name"].lower() for t in attention_tests)

    # Defaults if everything within range
    if not attention_tests:
        dos.extend([
            "Continue maintaining a nutrient-dense whole-food diet with diverse vegetables and lean proteins.",
            "Stay physically active with at least 150 minutes of moderate aerobic exercise weekly.",
            "Maintain optimal hydration (2 to 2.5 liters of water daily).",
            "Keep routine checkup schedules as recommended by your physician.",
        ])
        donts.extend([
            "Do not skip annual preventive health checkups even when current tests are within normal targets.",
            "Avoid prolonged sedentary periods during work or screen time.",
            "Limit consumption of ultra-processed snacks and added sugars.",
            "Avoid irregular sleep patterns.",
        ])
        diet.append("Incorporate antioxidant-rich fruits, leafy greens, legumes, and whole grains daily.")
        lifestyle.append("Aim for consistent 7 to 8 hours of restorative sleep each night.")
        questions.append("Based on my age and family health history, what routine screening timeline is optimal?")
    else:
        # Tailored guidance
        if has_lipid:
            dos.append("Prioritize heart-healthy fats (olive oil, avocados, nuts) and soluble fiber (oats, beans, chia).")
            donts.append("Minimize fried foods, commercial baked goods, and foods containing trans fats.")
            diet.append("Increase daily intake of omega-3 rich foods (flaxseeds, walnuts, fatty fish) and plant stanols.")
            lifestyle.append("Engage in consistent moderate-intensity cardiovascular exercise (e.g. 30 mins brisk walking 5 days/week).")
            questions.append("What are my specific cardiovascular target goals for LDL cholesterol and non-HDL cholesterol?")

        if has_liver:
            dos.append("Prioritize cruciferous vegetables (broccoli, cabbage), hydration, and antioxidant-rich foods.")
            donts.append("Avoid alcohol consumption and minimize unnecessary over-the-counter medications that strain hepatic metabolism.")
            diet.append("Limit high-fructose corn syrup, refined carbohydrates, and heavily fried meals.")
            lifestyle.append("Maintain a stable, healthy weight through gradual lifestyle modifications rather than crash diets.")
            questions.append("Would you recommend repeating liver function testing (LFT) in 4 to 8 weeks to monitor enzyme trajectories?")

        if has_sugar:
            dos.append("Choose complex carbohydrates with low glycemic index (quinoa, brown rice, steel-cut oats).")
            donts.append("Avoid sugary beverages, sweetened sodas, and refined flours that provoke rapid blood glucose spikes.")
            diet.append("Pair carbohydrates with lean protein and healthy fats to slow digestive glucose absorption.")
            lifestyle.append("Take a 10 to 15 minute light walk after major meals to support insulin sensitivity.")
            questions.append("Should we track fasting blood sugar or HbA1c periodically, and are there target ranges specific to my profile?")

        if has_uric:
            dos.append("Drink 2.5 to 3 liters of water daily to facilitate natural renal uric acid clearance.")
            donts.append("Limit high-purine foods such as organ meats, shellfish, and high-fructose beverages.")
            diet.append("Incorporate low-fat dairy products, cherries, and Vitamin C-rich foods.")
            lifestyle.append("Avoid rapid extreme fasting or dehydration, which can elevate serum uric acid concentration.")
            questions.append("What preventive lifestyle adjustments can help prevent uric acid accumulation and joint discomfort?")

        if has_hemoglobin:
            dos.append("Include iron-rich foods (spinach, lentils, fortified cereals) paired with Vitamin C (citrus, bell peppers) to boost absorption.")
            donts.append("Avoid drinking tea or coffee immediately with main meals, as tannins can inhibit dietary iron absorption.")
            diet.append("Include adequate folate and Vitamin B12 sources (eggs, legumes, nutritional yeast).")
            questions.append("Would it be beneficial to evaluate serum ferritin, iron saturation, or vitamin B12 levels?")

    # Fillers if fewer items
    if len(dos) < 3:
        dos.append("Maintain consistent hydration and structured sleep cycles.")
    if len(donts) < 3:
        donts.append("Do not make drastic changes to your medication regimen without consulting your physician.")
    if len(questions) < 2:
        questions.append("What follow-up timeline do you advise for monitoring these laboratory parameters?")

    summary = (
        f"This report contains {len(observations)} investigated parameters. "
        f"{len(attention_tests)} observation{'s' if len(attention_tests) != 1 else ''} differed from standard reference ranges. "
        f"The suggestions below provide structured educational guidance to support your overall wellness."
    )

    return HealthGuidance(
        report_id=report.id,
        report_type=report.report_type,
        report_date=str(report.report_date or report.upload_timestamp).split(" ")[0],
        urgent_alert=urgent_alert,
        general_summary=summary,
        dos=dos,
        donts=donts,
        diet_suggestions=diet,
        lifestyle_suggestions=lifestyle,
        doctor_questions=questions,
    )
