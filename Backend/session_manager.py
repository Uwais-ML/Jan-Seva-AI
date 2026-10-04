"""
Session state manager for multi-turn conversations and user demographic profiling.
"""

import asyncio
from typing import Dict, Any, List, Optional
from datetime import datetime
from Database.session import SessionLocal
from Database.models import UserProfileModel, ConversationLogModel


class UserSession:
    """Represents an active citizen interaction session."""

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.attributes: Dict[str, Any] = {}
        self.history: List[Dict[str, str]] = []
        self.interruption_event = asyncio.Event()
        self.created_at = datetime.utcnow()
        self.load_from_db()

    def load_from_db(self):
        """Loads saved user profile and persistent chat history from database."""
        with SessionLocal() as db:
            profile = db.query(UserProfileModel).filter_by(session_id=self.session_id).first()
            if profile:
                if profile.age is not None:
                    self.attributes["age"] = profile.age
                if profile.annual_income is not None:
                    self.attributes["annual_income"] = profile.annual_income
                if profile.monthly_income is not None:
                    self.attributes["monthly_income"] = profile.monthly_income
                if profile.state:
                    self.attributes["state"] = profile.state
                if profile.occupation:
                    self.attributes["occupation"] = profile.occupation
                if profile.gender:
                    self.attributes["gender"] = profile.gender

            # Load persistent dialogue turns
            logs = db.query(ConversationLogModel).filter_by(session_id=self.session_id).order_by(ConversationLogModel.timestamp.asc()).all()
            self.history = [
                {
                    "role": log.role,
                    "content": log.content,
                    "detected_language": log.detected_language,
                    "sources": log.sources or [],
                    "timestamp": log.timestamp.isoformat() if log.timestamp else ""
                }
                for log in logs
            ]

    def update_attributes(self, new_data: Dict[str, Any]):
        """Merges new extracted demographics and syncs to database."""
        if not new_data:
            return

        for k, v in new_data.items():
            if v is not None:
                self.attributes[k] = v

        with SessionLocal() as db:
            profile = db.query(UserProfileModel).filter_by(session_id=self.session_id).first()
            if not profile:
                profile = UserProfileModel(session_id=self.session_id)
                db.add(profile)

            if "age" in self.attributes:
                profile.age = self.attributes["age"]
            if "annual_income" in self.attributes:
                profile.annual_income = self.attributes["annual_income"]
            if "monthly_income" in self.attributes:
                profile.monthly_income = self.attributes["monthly_income"]
            if "state" in self.attributes:
                profile.state = self.attributes["state"]
            if "occupation" in self.attributes:
                profile.occupation = self.attributes["occupation"]
            if "gender" in self.attributes:
                profile.gender = self.attributes["gender"]

            db.commit()

    def add_message(self, role: str, content: str, language: Optional[str] = None, sources: Optional[List[str]] = None):
        """Adds dialogue turn to history and persists to conversation logs."""
        msg_entry = {
            "role": role,
            "content": content,
            "detected_language": language,
            "sources": sources or [],
            "timestamp": datetime.utcnow().isoformat()
        }
        self.history.append(msg_entry)
        with SessionLocal() as db:
            log = ConversationLogModel(
                session_id=self.session_id,
                role=role,
                content=content,
                detected_language=language,
                sources=sources or []
            )
            db.add(log)
            db.commit()

    def signal_interruption(self):
        """Signals current audio playback / generation to abort immediately."""
        self.interruption_event.set()

    def reset_interruption(self):
        """Resets the interruption flag for a new turn."""
        self.interruption_event.clear()


class SessionRegistry:
    """Global registry of in-memory active user sessions with persistent database backing."""

    def __init__(self):
        self._sessions: Dict[str, UserSession] = {}

    def get_or_create(self, session_id: str) -> UserSession:
        if session_id not in self._sessions:
            self._sessions[session_id] = UserSession(session_id)
        return self._sessions[session_id]

    def reset_session(self, session_id: str):
        if session_id in self._sessions:
            del self._sessions[session_id]
        with SessionLocal() as db:
            db.query(UserProfileModel).filter_by(session_id=session_id).delete()
            db.query(ConversationLogModel).filter_by(session_id=session_id).delete()
            from Database.models import EligibilityCheckModel
            db.query(EligibilityCheckModel).filter_by(session_id=session_id).delete()
            db.commit()


session_registry = SessionRegistry()
