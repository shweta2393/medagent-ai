import logging

from fastapi import APIRouter, HTTPException, UploadFile, File

from app.models.schemas import (
    DiagnosisRequest,
    DiagnosisResponse,
    FollowUpRequest,
    FollowUpResponse,
    SessionResponse,
    ChatRequest,
    ChatResponse,
)
from app.services.diagnosis_engine import DiagnosisEngine
from app.services.session_manager import SessionManager
from app.services.chat_service import get_chat_service
from app.services.lab_extractor import process_lab_file

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


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Send a message to the medical chatbot and get a RAG-grounded response."""
    try:
        result = get_chat_service().chat(
            message=request.message,
            session_id=request.session_id,
        )
        return result
    except RuntimeError as e:
        detail = str(e)
        if "quota" in detail.lower() or "rate" in detail.lower():
            raise HTTPException(
                status_code=429,
                detail="AI service rate limit reached. Please wait 1-2 minutes and try again.",
            )
        raise HTTPException(status_code=502, detail=detail)
    except Exception as e:
        logger.exception("Unexpected error in chat")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/chat/history/{session_id}")
async def chat_history(session_id: str):
    """Retrieve the message history for a chat session."""
    session = _get_sessions().get_chat_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Chat session not found")
    return {"session_id": session["id"], "messages": session["messages"]}


MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10 MB
ALLOWED_TYPES = {
    "application/pdf",
    "image/jpeg", "image/jpg", "image/png",
    "text/plain", "text/csv",
}


@router.post("/lab/extract")
async def extract_lab_from_file(file: UploadFile = File(...)):
    """Upload a lab report file and extract structured test results using LLM."""
    content_type = (file.content_type or "").lower()
    filename = file.filename or "unknown"

    if content_type not in ALLOWED_TYPES:
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        ext_map = {"pdf": "application/pdf", "jpg": "image/jpeg", "jpeg": "image/jpeg",
                    "png": "image/png", "txt": "text/plain", "csv": "text/csv"}
        content_type = ext_map.get(ext, content_type)
        if content_type not in ALLOWED_TYPES:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type. Accepted: PDF, JPG, PNG, TXT, CSV",
            )

    file_bytes = await file.read()
    if len(file_bytes) > MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=400, detail="File too large. Maximum size is 10 MB.")
    if len(file_bytes) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    try:
        results = await process_lab_file(file_bytes, content_type, filename)
        return {"status": "success", "count": len(results), "lab_values": results}
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.exception("Error extracting lab values from %s", filename)
        raise HTTPException(status_code=500, detail="Failed to extract lab values. Please try again or enter manually.")


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
