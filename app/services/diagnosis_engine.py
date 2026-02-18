import logging
from typing import Optional

from app.models.schemas import (
    DiagnosisRequest,
    DiagnosisResponse,
    DiseasePrediction,
    FollowUpRequest,
    FollowUpResponse,
    RecommendedTest,
    UrgencyLevel,
)
from app.services.llm_service import get_llm_service
from app.services.rag_service import get_rag_service
from app.services.session_manager import SessionManager

logger = logging.getLogger(__name__)

DIAGNOSIS_SYSTEM_PROMPT = """You are MedAgent AI, an expert clinical decision support system. 
You analyze patient symptoms, vitals, lab reports, and medical history to provide differential diagnoses.

IMPORTANT RULES:
1. Always provide multiple differential diagnoses ranked by likelihood
2. Assign confidence scores (0.0 to 1.0) based on how well symptoms match
3. Consider patient demographics (age, gender) in your analysis
4. Flag critical/emergency conditions with appropriate urgency
5. Suggest relevant follow-up questions to narrow the diagnosis
6. Recommend appropriate diagnostic tests
7. Recommend relevant specialist referrals
8. Always include a general advice section
9. Be thorough but concise
10. Never provide definitive diagnoses - this is a decision SUPPORT tool

You have access to a medical knowledge base. Use the provided context to ground your analysis.
"""

DIAGNOSIS_JSON_SCHEMA = """{
    "predictions": [
        {
            "disease": "Disease name",
            "confidence": 0.85,
            "description": "Brief description of the disease and why it matches",
            "key_matching_factors": ["factor1", "factor2"]
        }
    ],
    "follow_up_questions": ["question1", "question2", "question3"],
    "recommended_tests": [
        {
            "test_name": "Test name",
            "reason": "Why this test is recommended",
            "priority": "high/medium/low"
        }
    ],
    "recommended_specialists": ["Specialist1", "Specialist2"],
    "urgency_level": "low/moderate/high/critical",
    "urgency_reasoning": "Explanation of urgency assessment",
    "general_advice": "General health advice for the patient"
}"""


def _format_patient_context(req: DiagnosisRequest) -> str:
    """Build a human-readable patient summary from the request."""
    parts = [f"**Symptoms**: {', '.join(req.symptoms)}"]

    if req.symptom_duration:
        parts.append(f"**Duration**: {req.symptom_duration}")

    if req.patient_info:
        info = req.patient_info
        demo = []
        if info.age is not None:
            demo.append(f"Age: {info.age}")
        if info.gender:
            demo.append(f"Gender: {info.gender}")
        if info.weight_kg:
            demo.append(f"Weight: {info.weight_kg} kg")
        if info.height_cm:
            demo.append(f"Height: {info.height_cm} cm")
        if demo:
            parts.append(f"**Demographics**: {', '.join(demo)}")

    if req.vitals:
        v = req.vitals
        vitals_items = []
        if v.blood_pressure_systolic and v.blood_pressure_diastolic:
            vitals_items.append(f"BP: {v.blood_pressure_systolic}/{v.blood_pressure_diastolic} mmHg")
        if v.heart_rate:
            vitals_items.append(f"HR: {v.heart_rate} bpm")
        if v.temperature_f:
            vitals_items.append(f"Temp: {v.temperature_f}°F")
        if v.respiratory_rate:
            vitals_items.append(f"RR: {v.respiratory_rate}/min")
        if v.oxygen_saturation:
            vitals_items.append(f"SpO2: {v.oxygen_saturation}%")
        if vitals_items:
            parts.append(f"**Vitals**: {', '.join(vitals_items)}")

    if req.medical_history:
        parts.append(f"**Medical History**: {', '.join(req.medical_history)}")

    if req.current_medications:
        parts.append(f"**Current Medications**: {', '.join(req.current_medications)}")

    if req.lab_reports:
        lab_lines = []
        for lab in req.lab_reports:
            line = f"  - {lab.name}: {lab.value}"
            if lab.when:
                line += f" (taken: {lab.when})"
            lab_lines.append(line)
        parts.append(f"**Lab Reports**:\n" + "\n".join(lab_lines))

    if req.lifestyle:
        parts.append(f"**Lifestyle**: {req.lifestyle}")

    if req.additional_notes:
        parts.append(f"**Additional Notes**: {req.additional_notes}")

    missing = []
    if not req.patient_info or (req.patient_info.age is None and not req.patient_info.gender):
        missing.append("patient demographics (age, gender)")
    if not req.vitals:
        missing.append("vital signs")
    if not req.lab_reports:
        missing.append("lab reports")
    if not req.medical_history:
        missing.append("medical history")
    if missing:
        parts.append(f"**Not provided**: {', '.join(missing)} — consider asking about these in follow-up questions")

    return "\n".join(parts)


class DiagnosisEngine:
    def __init__(self):
        self.llm = get_llm_service()
        self.rag = get_rag_service()
        self.sessions = SessionManager()

    def diagnose(self, request: DiagnosisRequest) -> DiagnosisResponse:
        """Run the full diagnosis pipeline."""
        session_id = request.session_id or self.sessions.create_session()

        additional_info_parts = []
        if request.patient_info:
            if request.patient_info.age:
                additional_info_parts.append(f"Age: {request.patient_info.age}")
            if request.patient_info.gender:
                additional_info_parts.append(f"Gender: {request.patient_info.gender}")
        if request.medical_history:
            additional_info_parts.append(f"History: {', '.join(request.medical_history)}")

        rag_context = self.rag.build_context(
            symptoms=request.symptoms,
            additional_info=" ".join(additional_info_parts),
        )

        patient_context = _format_patient_context(request)

        prompt = f"""{DIAGNOSIS_SYSTEM_PROMPT}

--- MEDICAL KNOWLEDGE BASE CONTEXT ---
{rag_context}
--- END CONTEXT ---

--- PATIENT INFORMATION ---
{patient_context}
--- END PATIENT INFORMATION ---

Based on the patient information and the medical knowledge context, provide a comprehensive clinical assessment.

Respond in this exact JSON format:
{DIAGNOSIS_JSON_SCHEMA}

Provide 3-5 differential diagnoses ranked by confidence. Include at least 3 follow-up questions 
that would help narrow the diagnosis. Recommend relevant tests and specialists.
Assess the urgency level carefully based on the symptoms, vitals, and overall clinical picture."""

        try:
            result = self.llm.generate_json(prompt)
        except Exception as e:
            logger.error(f"LLM generation failed: {e}")
            raise RuntimeError(f"Diagnosis generation failed: {e}")

        predictions = [
            DiseasePrediction(**p) for p in result.get("predictions", [])
        ]
        recommended_tests = [
            RecommendedTest(**t) for t in result.get("recommended_tests", [])
        ]
        urgency_raw = result.get("urgency_level", "moderate").lower()
        try:
            urgency = UrgencyLevel(urgency_raw)
        except ValueError:
            urgency = UrgencyLevel.MODERATE

        self.sessions.add_interaction(session_id, {
            "type": "diagnosis",
            "request": request.model_dump(),
            "predictions": [p.model_dump() for p in predictions],
        })

        return DiagnosisResponse(
            session_id=session_id,
            predictions=predictions,
            follow_up_questions=result.get("follow_up_questions", []),
            recommended_tests=recommended_tests,
            recommended_specialists=result.get("recommended_specialists", []),
            urgency_level=urgency,
            urgency_reasoning=result.get("urgency_reasoning", ""),
            general_advice=result.get("general_advice", ""),
        )

    def handle_followup(self, request: FollowUpRequest) -> FollowUpResponse:
        """Process follow-up answers and refine the diagnosis."""
        session = self.sessions.get_session(request.session_id)
        if not session:
            raise ValueError(f"Session {request.session_id} not found")

        previous_interactions = session.get("interactions", [])
        previous_context = ""
        original_symptoms = []
        for interaction in previous_interactions:
            if interaction["type"] == "diagnosis":
                orig_req = interaction["request"]
                original_symptoms = orig_req.get("symptoms", [])
                prev_predictions = interaction.get("predictions", [])
                previous_context += (
                    f"Original symptoms: {', '.join(original_symptoms)}\n"
                    f"Previous predictions: {prev_predictions}\n"
                )

        answers_text = "\n".join(
            f"Q: {q}\nA: {a}" for q, a in request.answers.items()
        )

        rag_context = self.rag.build_context(
            symptoms=original_symptoms,
            additional_info=answers_text,
        )

        prompt = f"""{DIAGNOSIS_SYSTEM_PROMPT}

--- MEDICAL KNOWLEDGE BASE CONTEXT ---
{rag_context}
--- END CONTEXT ---

--- PREVIOUS CLINICAL CONTEXT ---
{previous_context}
--- END PREVIOUS CONTEXT ---

--- FOLLOW-UP ANSWERS ---
{answers_text}
--- END FOLLOW-UP ANSWERS ---

Based on the follow-up answers and previous context, provide an updated clinical assessment.
The follow-up answers should help refine or change the differential diagnoses.

Respond in this exact JSON format:
{DIAGNOSIS_JSON_SCHEMA}

Provide updated differential diagnoses accounting for the new information. If the answers narrow 
down the possibilities, adjust confidence scores accordingly. Include additional follow-up questions 
if needed to further refine the diagnosis."""

        try:
            result = self.llm.generate_json(prompt)
        except Exception as e:
            logger.error(f"Follow-up LLM generation failed: {e}")
            raise RuntimeError(f"Follow-up generation failed: {e}")

        predictions = [
            DiseasePrediction(**p) for p in result.get("predictions", [])
        ]
        recommended_tests = [
            RecommendedTest(**t) for t in result.get("recommended_tests", [])
        ]
        urgency_raw = result.get("urgency_level", "moderate").lower()
        try:
            urgency = UrgencyLevel(urgency_raw)
        except ValueError:
            urgency = UrgencyLevel.MODERATE

        self.sessions.add_interaction(request.session_id, {
            "type": "followup",
            "answers": request.answers,
            "predictions": [p.model_dump() for p in predictions],
        })

        return FollowUpResponse(
            session_id=request.session_id,
            updated_predictions=predictions,
            additional_questions=result.get("follow_up_questions", []),
            recommended_tests=recommended_tests,
            recommended_specialists=result.get("recommended_specialists", []),
            urgency_level=urgency,
            urgency_reasoning=result.get("urgency_reasoning", ""),
            general_advice=result.get("general_advice", ""),
        )
