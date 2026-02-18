import uuid
import time
import threading
from typing import Optional


class SessionManager:
    """In-memory session store for diagnosis and chat conversations."""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._sessions: dict[str, dict] = {}
                    cls._instance._chat_sessions: dict[str, dict] = {}
        return cls._instance

    def create_session(self) -> str:
        session_id = str(uuid.uuid4())
        self._sessions[session_id] = {
            "id": session_id,
            "created_at": time.time(),
            "interactions": [],
        }
        return session_id

    def get_session(self, session_id: str) -> Optional[dict]:
        return self._sessions.get(session_id)

    def add_interaction(self, session_id: str, interaction: dict):
        session = self._sessions.get(session_id)
        if session is None:
            session_id_new = self.create_session()
            session = self._sessions[session_id_new]
        interaction["timestamp"] = time.time()
        session["interactions"].append(interaction)

    def list_sessions(self) -> list[dict]:
        return [
            {"id": s["id"], "created_at": s["created_at"], "interaction_count": len(s["interactions"])}
            for s in self._sessions.values()
        ]

    # --- Chat sessions ---

    def create_chat_session(self) -> str:
        session_id = str(uuid.uuid4())
        self._chat_sessions[session_id] = {
            "id": session_id,
            "created_at": time.time(),
            "messages": [],
        }
        return session_id

    def add_chat_message(self, session_id: str, role: str, content: str):
        if session_id not in self._chat_sessions:
            self._chat_sessions[session_id] = {
                "id": session_id,
                "created_at": time.time(),
                "messages": [],
            }
        self._chat_sessions[session_id]["messages"].append({
            "role": role,
            "content": content,
            "timestamp": time.time(),
        })

    def get_chat_history(self, session_id: str) -> list[dict]:
        session = self._chat_sessions.get(session_id)
        return session["messages"] if session else []

    def get_chat_session(self, session_id: str) -> Optional[dict]:
        return self._chat_sessions.get(session_id)
