"""Short-term conversation memory for the answer endpoint (06 §3).

Follow-ups like "what about the one from last year?" are resolved against
the prior turns of the same session instead of the raw query alone. Sessions
are in-memory only (single-user app), idle-expiring and turn-capped.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from uuid import uuid4

from backend.config import settings


@dataclass
class Turn:
    role: str  # "user" | "assistant"
    content: str


@dataclass
class _Session:
    session_id: str
    turns: list[Turn] = field(default_factory=list)
    last_used: float = field(default_factory=time.time)

    def touch(self) -> None:
        self.last_used = time.time()


class SessionStore:
    def __init__(self, ttl_seconds: int | None = None, max_turns: int | None = None):
        self._ttl = ttl_seconds if ttl_seconds is not None else settings.answer_session_ttl_seconds
        self._max_turns = max_turns if max_turns is not None else settings.answer_history_turns
        self._sessions: dict[str, _Session] = {}
        self._lock = threading.Lock()

    def prune(self) -> None:
        """Drop idle-expired sessions (called on every access)."""
        cutoff = time.time() - self._ttl
        with self._lock:
            for sid in [s for s, v in self._sessions.items() if v.last_used < cutoff]:
                del self._sessions[sid]

    def get_or_create(self, session_id: str | None) -> tuple[str, list[Turn]]:
        """Return (session_id, history). Creates a session when absent/unknown."""
        self.prune()
        with self._lock:
            if session_id and session_id in self._sessions:
                sess = self._sessions[session_id]
                sess.touch()
            else:
                # Unknown/expired ids never resurrect: start a fresh session.
                sess = _Session(session_id=uuid4().hex)
                self._sessions[sess.session_id] = sess
            # history is the *prior* turns (each turn = user + assistant msg)
            return sess.session_id, list(sess.turns[-2 * self._max_turns :])

    def append(self, session_id: str, user: str, assistant: str) -> None:
        self.prune()
        with self._lock:
            sess = self._sessions.get(session_id)
            if sess is None:
                sess = _Session(session_id=session_id)
                self._sessions[session_id] = sess
            sess.turns.append(Turn(role="user", content=user))
            sess.turns.append(Turn(role="assistant", content=assistant))
            sess.turns = sess.turns[-2 * self._max_turns :]
            sess.touch()


sessions = SessionStore()
