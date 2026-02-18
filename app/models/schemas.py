from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum


class UrgencyLevel(str, Enum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"


class PatientInfo(BaseModel):
    age: Optional[int] = Field(None, ge=0, le=150, description="Patient age")
    gender: Optional[str] = Field(None, description="Patient gender")
    weight_kg: Optional[float] = Field(None, description="Weight in kg")
    height_cm: Optional[float] = Field(None, description="Height in cm")


class Vitals(BaseModel):
    blood_pressure_systolic: Optional[int] = Field(None, description="Systolic BP mmHg")
    blood_pressure_diastolic: Optional[int] = Field(None, description="Diastolic BP mmHg")
    heart_rate: Optional[int] = Field(None, description="Heart rate bpm")
    temperature_f: Optional[float] = Field(None, description="Temperature in Fahrenheit")
    respiratory_rate: Optional[int] = Field(None, description="Breaths per minute")
    oxygen_saturation: Optional[float] = Field(None, description="SpO2 percentage")


class LabReport(BaseModel):
    name: str = Field(..., description="Lab test name, e.g. HbA1c")
    value: str = Field(..., description="Test result value, e.g. 7.2%")
    when: Optional[str] = Field(None, description="When the test was taken, e.g. 'Today', '2 weeks ago'")


class DiagnosisRequest(BaseModel):
    session_id: Optional[str] = None
    symptoms: list[str] = Field(..., min_length=1, description="List of symptoms")
    symptom_duration: Optional[str] = Field(None, description="e.g., '3 days', '2 weeks'")
    patient_info: Optional[PatientInfo] = None
    vitals: Optional[Vitals] = None
    medical_history: Optional[list[str]] = Field(default=None, description="Past conditions")
    current_medications: Optional[list[str]] = Field(default=None, description="Current meds")
    lab_reports: Optional[list[LabReport]] = Field(default=None, description="Lab test results with optional dates")
    lifestyle: Optional[str] = Field(None, description="Smoking, alcohol, exercise, diet")
    additional_notes: Optional[str] = None


class DiseasePrediction(BaseModel):
    disease: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    description: str
    key_matching_factors: list[str]


class RecommendedTest(BaseModel):
    test_name: str
    reason: str
    priority: str


class DiagnosisResponse(BaseModel):
    session_id: str
    predictions: list[DiseasePrediction]
    follow_up_questions: list[str]
    recommended_tests: list[RecommendedTest]
    recommended_specialists: list[str]
    urgency_level: UrgencyLevel
    urgency_reasoning: str
    general_advice: str
    disclaimer: str = (
        "This is an AI-assisted clinical decision support tool and is NOT a substitute "
        "for professional medical advice. Always consult a qualified healthcare provider "
        "for diagnosis and treatment decisions."
    )


class FollowUpRequest(BaseModel):
    session_id: str
    answers: dict[str, str] = Field(..., description="question -> answer mapping")


class FollowUpResponse(BaseModel):
    session_id: str
    updated_predictions: list[DiseasePrediction]
    additional_questions: list[str]
    recommended_tests: list[RecommendedTest]
    recommended_specialists: list[str]
    urgency_level: UrgencyLevel
    urgency_reasoning: str
    general_advice: str
    disclaimer: str = (
        "This is an AI-assisted clinical decision support tool and is NOT a substitute "
        "for professional medical advice. Always consult a qualified healthcare provider "
        "for diagnosis and treatment decisions."
    )


class SessionResponse(BaseModel):
    session_id: str
    interactions: list[dict]
    current_predictions: Optional[list[DiseasePrediction]] = None


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, description="User message")
    session_id: Optional[str] = Field(None, description="Chat session ID for conversation continuity")


class ChatMessage(BaseModel):
    role: str
    content: str
    timestamp: Optional[float] = None


class ChatResponse(BaseModel):
    reply: str
    session_id: str
    sources: list[str] = Field(default_factory=list, description="RAG topics used to ground the response")
