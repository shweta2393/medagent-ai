import logging

from fastapi import APIRouter, HTTPException

from app.models.schemas import (
    DiagnosisRequest,
    DiagnosisResponse,
    FollowUpRequest,
    FollowUpResponse,
    SessionResponse,
)
from app.services.diagnosis_engine import DiagnosisEngine
from app.services.session_manager import SessionManager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["diagnosis"])

engine = None
sessions = None


def _get_engine() -> DiagnosisEngine:
    global engine
    if engine is None:
        engine = DiagnosisEngine()
    return engine


def _get_sessions() -> SessionManager:
    global sessions
    if sessions is None:
        sessions = SessionManager()
    return sessions


@router.post("/diagnose", response_model=DiagnosisResponse)
async def diagnose(request: DiagnosisRequest):
    """
    Analyze patient symptoms, vitals, lab reports, and history to generate
    differential diagnoses with confidence scores, follow-up questions,
    recommended tests, specialist referrals, and urgency assessment.
    """
    try:
        result = _get_engine().diagnose(request)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        detail = str(e)
        if "quota" in detail.lower() or "rate" in detail.lower():
            raise HTTPException(
                status_code=429,
                detail="AI service rate limit reached. Please wait 1-2 minutes and try again.",
            )
        raise HTTPException(status_code=502, detail=detail)
    except Exception as e:
        logger.exception("Unexpected error during diagnosis")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/followup", response_model=FollowUpResponse)
async def followup(request: FollowUpRequest):
    """
    Submit answers to follow-up questions and receive refined diagnoses
    based on the additional information.
    """
    try:
        result = _get_engine().handle_followup(request)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        detail = str(e)
        if "quota" in detail.lower() or "rate" in detail.lower():
            raise HTTPException(
                status_code=429,
                detail="AI service rate limit reached. Please wait 1-2 minutes and try again.",
            )
        raise HTTPException(status_code=502, detail=detail)
    except Exception as e:
        logger.exception("Unexpected error during follow-up")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/session/{session_id}", response_model=SessionResponse)
async def get_session(session_id: str):
    """Retrieve the full interaction history for a session."""
    session = _get_sessions().get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    predictions = None
    for interaction in reversed(session.get("interactions", [])):
        if "predictions" in interaction:
            from app.models.schemas import DiseasePrediction
            predictions = [DiseasePrediction(**p) for p in interaction["predictions"]]
            break

    return SessionResponse(
        session_id=session["id"],
        interactions=session["interactions"],
        current_predictions=predictions,
    )


@router.get("/sessions")
async def list_sessions():
    """List all active diagnosis sessions."""
    return _get_sessions().list_sessions()


@router.get("/health")
async def health_check():
    """Health check endpoint with provider info."""
    from app.services.llm_service import get_llm_service
    try:
        llm_info = get_llm_service().get_provider_info()
    except Exception:
        llm_info = {"error": "LLM service not initialized"}
    return {"status": "healthy", "service": "MedAgent AI", "llm": llm_info}


@router.get("/rag/stats")
async def rag_stats():
    """Get vector DB statistics - shows embedded medical knowledge info."""
    from app.services.rag_service import get_rag_service
    rag = get_rag_service()
    return rag.get_stats()


@router.post("/rag/reindex")
async def rag_reindex():
    """Force re-index the medical knowledge base into the vector DB."""
    from app.services.rag_service import get_rag_service
    rag = get_rag_service()
    rag.collection.delete(where={})
    rag._ingest_knowledge_base()
    return {"status": "reindexed", **rag.get_stats()}
