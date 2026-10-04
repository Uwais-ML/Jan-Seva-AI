"""
Unit tests for Persistent State Record of Chat Dialogue and Summarize-First synthesis.
"""

import sys
import unittest
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from Database.session import SessionLocal, init_db
from Database.models import ConversationLogModel, UserProfileModel
from Backend.session_manager import UserSession, session_registry
from Backend.agent_orchestrator import orchestrator
from RAG.Retrival import Retrival


class TestChatPersistenceAndSummary(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        init_db()

    async def test_persistent_chat_record_in_db(self):
        """Verify dialogue turns persist in database across new session instances."""
        test_session_id = "test_persist_uuid_99"

        # 1. Clear any prior test state
        session_registry.reset_session(test_session_id)

        # 2. Add turn via orchestrator
        res = await orchestrator.handle_user_input(
            session_id=test_session_id,
            user_text="Mera umar 26 saal hai, mujhe skill training chahiye"
        )
        self.assertIn("response", res)

        # 3. Inspect database directly
        with SessionLocal() as db:
            logs = db.query(ConversationLogModel).filter_by(session_id=test_session_id).order_by(ConversationLogModel.timestamp.asc()).all()
            self.assertEqual(len(logs), 2)  # 1 user + 1 assistant
            self.assertEqual(logs[0].role, "user")
            self.assertEqual(logs[1].role, "assistant")
            self.assertGreater(len(logs[1].content), 10)

        # 4. Create fresh in-memory session object for same ID to simulate reload/restart
        fresh_session = UserSession(test_session_id)
        self.assertEqual(len(fresh_session.history), 2)
        self.assertEqual(fresh_session.history[0]["role"], "user")
        self.assertEqual(fresh_session.history[1]["role"], "assistant")
        self.assertEqual(fresh_session.attributes.get("age"), 26)

    def test_summarize_first_in_rag_response(self):
        """Verify that the AI response introduces the scheme conversationally and offers help."""
        retriever = Retrival()

        # Test English — should mention PMKVY and offer further help
        res_en = retriever.get_grounded_answer("Tell me about PMKVY scheme", language="en")
        answer_en = res_en["answer"].lower()
        self.assertTrue(
            "pmkvy" in answer_en or "kaushal" in answer_en or "skill" in answer_en,
            f"Expected scheme mention, got: {res_en['answer'][:120]}"
        )
        # Should not contain raw markdown formatting
        self.assertNotIn("**Summary:**", res_en["answer"])
        self.assertNotIn("**Key Highlights:**", res_en["answer"])

        # Test Hinglish — should mention Ayushman Bharat naturally
        res_hinglish = retriever.get_grounded_answer("Ayushman Bharat ke baare mein batao", language="hinglish")
        answer_hi = res_hinglish["answer"].lower()
        self.assertTrue(
            "ayushman" in answer_hi or "health" in answer_hi or "hospital" in answer_hi,
            f"Expected scheme mention, got: {res_hinglish['answer'][:120]}"
        )
        self.assertNotIn("**Summary:**", res_hinglish["answer"])

        # Test Hindi — should mention PM-KISAN naturally in Hindi
        res_hi = retriever.get_grounded_answer("पीएम किसान योजना क्या है", language="hi")
        answer_raw = res_hi["answer"]
        self.assertTrue(
            "किसान" in answer_raw or "kisan" in answer_raw.lower() or "सम्मान" in answer_raw,
            f"Expected scheme mention, got: {answer_raw[:120]}"
        )
        self.assertNotIn("**संक्षेप (Summary):**", answer_raw)



if __name__ == "__main__":
    unittest.main()
