"""RAG chains — AI chat with hybrid retrieval (structured DB + ChromaDB + Gemini)."""

import logging
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from app.database.repositories import ObservationRepository, ReportRepository
from app.rag.vector_service import vector_service

logger = logging.getLogger(__name__)

MANDATORY_DISCLAIMER = (
    "AI-generated health insights are informational and not a substitute for professional medical advice. "
    "Please consult a healthcare professional for medical concerns."
)

SYSTEM_PROMPT = f"""You are a helpful, professional medical report assistant for HealthTrack AI. You help users understand their medical reports and longitudinal health trends in clear, simple language.

IMPORTANT RULES:
1. You are NOT a doctor. Do not diagnose diseases, recommend prescriptions, or adjust medication dosages.
2. Base your answers strictly on the provided report data and context. Do not fabricate or invent values.
3. If data is not present in the records, state that clearly.
4. When values are outside reference ranges, explain what the test measures and what deviation typically means in an educational, reassuring context.
5. Format your answers clearly using clean Markdown (bullet points, bold key test names and values, concise paragraphs).
6. Perform no mathematical calculations yourself — use only the pre-calculated trend data provided."""


def get_report_chat_response(
    db: Session,
    api_key: str,
    model_name: str,
    question: str,
    patient_id: str,
    report_id: str,
) -> Dict[str, Any]:
    """Chat about a specific report using ChromaDB context + structured data."""
    import google.generativeai as genai

    # 1. Get report observations from structured DB
    observations = ObservationRepository.get_for_report(db, report_id, patient_id)
    report = ReportRepository.get_by_id(db, report_id, patient_id)

    # 2. Get relevant chunks from Vector DB (scoped to this report)
    chroma_results = vector_service.search(
        question,
        patient_id,
        report_id=report_id,
        n_results=5,
        api_key=api_key,
        db=db,
    )

    # 3. Build context
    context_parts = []

    if report:
        context_parts.append(f"Report: {report.report_type or 'Medical Report'}")
        context_parts.append(f"Date: {report.report_date or report.upload_timestamp}")
        context_parts.append(f"Laboratory: {report.laboratory or 'Unknown'}")

    if observations:
        context_parts.append("\nTest Results:")
        for obs in observations:
            line = f"- {obs.test_name}: {obs.value_text or 'N/A'}"
            if obs.unit:
                line += f" {obs.unit}"
            if obs.reference_text:
                line += f" (ref: {obs.reference_text})"
            if obs.status and obs.status != "unknown":
                line += f" [{obs.status.replace('_', ' ').title()}]"
            context_parts.append(line)

    if chroma_results:
        context_parts.append("\nAdditional Report Context:")
        for result in chroma_results:
            context_parts.append(result["text"][:500])

    context = "\n".join(context_parts)

    # 4. Generate response
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(model_name, system_instruction=SYSTEM_PROMPT)

    prompt = f"""Context from the medical report:\n{context}\n\nUser question: {question}"""
    response = model.generate_content(prompt)

    # 5. Build sources
    sources = []
    if report:
        sources.append({
            "report_id": report.id,
            "report_type": report.report_type,
            "report_date": str(report.report_date) if report.report_date else None,
            "page_number": None,
            "text": f"{report.report_type or 'Report'} — {report.report_date or 'Unknown date'}",
        })

    for result in chroma_results:
        if result.get("metadata", {}).get("page_number"):
            sources.append({
                "report_id": result.get("report_id"),
                "report_type": result.get("report_type"),
                "report_date": result.get("report_date"),
                "page_number": result["metadata"].get("page_number"),
                "text": f"Page {result['metadata']['page_number']}",
            })

    return {
        "response": response.text.strip(),
        "sources": sources,
        "disclaimer": MANDATORY_DISCLAIMER,
    }


def get_history_chat_response(
    db: Session,
    api_key: str,
    model_name: str,
    question: str,
    patient_id: str,
) -> Dict[str, Any]:
    """Chat across the patient's medical history using hybrid retrieval."""
    import google.generativeai as genai

    # 1. Search Vector DB for relevant context
    chroma_results = vector_service.search(
        question,
        patient_id,
        n_results=10,
        api_key=api_key,
        db=db,
    )

    # 2. Check if question involves trends/comparisons — use structured DB
    trend_keywords = ["change", "trend", "compare", "previous", "increased", "decreased",
                      "improving", "worsening", "over time", "history", "progress"]
    is_trend_question = any(kw in question.lower() for kw in trend_keywords)

    trend_context = ""
    trend_data = None
    if is_trend_question:
        # Try to identify which test the user is asking about
        available_tests = ObservationRepository.get_available_tests(db, patient_id)
        for test_info in available_tests:
            test_name = test_info["canonical_name"].lower()
            if test_name.lower() in question.lower() or test_info.get("display_name", "").lower() in question.lower():
                # Get trend data from structured DB
                from app.api.dashboard import _compute_trend
                trend = _compute_trend(db, patient_id, test_info["canonical_name"])
                if trend and trend.data_points:
                    trend_context += f"\n\nTrend data for {test_info['canonical_name']}:\n"
                    for dp in trend.data_points:
                        trend_context += f"  - {dp.date}: {dp.value} {dp.unit or ''} [{dp.status}]\n"
                    if trend.absolute_change is not None:
                        trend_context += f"  Change: {trend.absolute_change:+.2f}"
                        if trend.percentage_change is not None:
                            trend_context += f" ({trend.percentage_change:+.1f}%)"
                        trend_context += f"\n  Direction: {trend.direction}\n"
                    trend_data = trend.model_dump()
                break

    # 3. Get latest attention items
    attention = ObservationRepository.get_attention_items(db, patient_id, limit=5)
    attention_context = ""
    if attention:
        attention_context = "\n\nCurrent items needing attention:\n"
        for obs in attention:
            attention_context += f"- {obs.test_name}: {obs.value_text} {obs.unit or ''} [{obs.status}] ({obs.report_date})\n"

    # 4. Build context
    context_parts = []
    if chroma_results:
        context_parts.append("Relevant report sections:")
        for result in chroma_results:
            meta = result.get("metadata", {})
            header = f"[Report: {meta.get('report_type', '?')}, Date: {meta.get('report_date', '?')}]"
            context_parts.append(f"{header}\n{result['text'][:500]}")

    if trend_context:
        context_parts.append(trend_context)
    if attention_context:
        context_parts.append(attention_context)

    context = "\n\n".join(context_parts)

    # 5. Generate response
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(model_name, system_instruction=SYSTEM_PROMPT)

    prompt = f"""Patient medical history context:\n{context}\n\nUser question: {question}"""
    response = model.generate_content(prompt)

    # 6. Build sources
    sources = []
    seen_reports = set()
    for result in chroma_results:
        rid = result.get("report_id")
        if rid and rid not in seen_reports:
            seen_reports.add(rid)
            sources.append({
                "report_id": rid,
                "report_type": result.get("report_type"),
                "report_date": result.get("report_date"),
                "page_number": result.get("page_number"),
                "text": f"{result.get('report_type', 'Report')} — {result.get('report_date', 'Unknown')}",
            })

    return {
        "response": response.text.strip(),
        "sources": sources,
        "trend_data": trend_data,
        "disclaimer": MANDATORY_DISCLAIMER,
    }
