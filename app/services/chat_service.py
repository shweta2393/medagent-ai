import logging
from app.services.llm_service import get_llm_service
from app.services.rag_service import get_rag_service
from app.services.session_manager import SessionManager

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are MedAgent AI, a knowledgeable medical assistant. "
    "You help users understand symptoms, diseases, medications, and general health topics. "
    "Always be clear, empathetic, and factual. Use the provided medical knowledge context "
    "to ground your answers. If you are uncertain, say so.\n\n"
    "IMPORTANT RULES:\n"
    "- You are NOT a doctor. Always recommend consulting a healthcare professional for diagnosis and treatment.\n"
    "- Never prescribe medication or provide specific dosages.\n"
    "- If the user describes an emergency (chest pain, difficulty breathing, severe bleeding, etc.), "
    "immediately advise them to call emergency services.\n"
    "- Keep responses concise but thorough (2-4 paragraphs max).\n"
    "- Use simple language; avoid excessive medical jargon.\n"
)

MAX_HISTORY_MESSAGES = 10


class ChatService:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def chat(self, message: str, session_id: str | None = None) -> dict:
        sessions = SessionManager()
        llm = get_llm_service()
        rag = get_rag_service()

        if not session_id:
            session_id = sessions.create_chat_session()

        history = sessions.get_chat_history(session_id)
        sessions.add_chat_message(session_id, "user", message)

        rag_results = rag.retrieve(message, top_k=3)
        context = self._build_rag_context(rag_results)
        sources = self._extract_sources(rag_results)

        prompt = self._build_prompt(message, history, context)

        try:
            reply = llm.generate(prompt, temperature=0.4)
        except Exception as e:
            logger.error(f"Chat LLM error: {e}")
            raise

        sessions.add_chat_message(session_id, "assistant", reply)
        return {"reply": reply, "session_id": session_id, "sources": sources}

    def _build_rag_context(self, results: list[dict]) -> str:
        if not results:
            return ""
        parts = []
        for r in results:
            meta = r.get("metadata", {})
            disease = meta.get("disease", "General")
            parts.append(f"[{disease}] {r['content'][:500]}")
        return "\n\n".join(parts)

    def _extract_sources(self, results: list[dict]) -> list[str]:
        seen = set()
        sources = []
        for r in results:
            disease = r.get("metadata", {}).get("disease", "")
            if disease and disease not in seen:
                seen.add(disease)
                sources.append(disease)
        return sources

    def _build_prompt(self, message: str, history: list[dict], context: str) -> str:
        parts = [SYSTEM_PROMPT]

        if context:
            parts.append(f"MEDICAL KNOWLEDGE CONTEXT:\n{context}\n")

        if history:
            recent = history[-MAX_HISTORY_MESSAGES:]
            parts.append("CONVERSATION HISTORY:")
            for msg in recent:
                role = "User" if msg["role"] == "user" else "Assistant"
                parts.append(f"{role}: {msg['content']}")
            parts.append("")

        parts.append(f"User: {message}")
        parts.append("Assistant:")
        return "\n".join(parts)


def get_chat_service() -> ChatService:
    return ChatService()
