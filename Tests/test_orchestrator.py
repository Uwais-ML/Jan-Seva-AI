"""
Integration tests for the central Agent Orchestrator.
Tests end-to-end flow from multilingual input to grounded answer & eligibility.
"""

import sys
import asyncio
import unittest
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from Backend.agent_orchestrator import orchestrator
from Backend.session_manager import session_registry
from Database.session import init_db


class TestAgentOrchestrator(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        init_db()

    async def test_hinglish_skill_training_flow(self):
        """Tests that Hinglish query triggers Hinglish response, PMKVY scheme, and extracted age."""
        session_id = "test_orch_hinglish"
        query = "Mera umar 21 saal hai, mujhe free skill training course karna hai"

        result = await orchestrator.handle_user_input(
            session_id=session_id,
            user_text=query
        )

        self.assertEqual(result["detected_language"], "hinglish")
        self.assertEqual(result["extracted_attributes"].get("age"), 21)
        self.assertGreater(len(result["eligible_schemes"]), 0)

        # Check that PMKVY was matched
        scheme_ids = [s["scheme_id"] for s in result["eligible_schemes"]]
        self.assertIn("pmkvy", scheme_ids)
        self.assertGreater(len(result["sources"]), 0)

    async def test_english_ayushman_flow(self):
        """Tests English healthcare query and income extraction."""
        session_id = "test_orch_english"
        query = "I earn 1.5 lakh annually and need hospital health insurance for my family"

        result = await orchestrator.handle_user_input(
            session_id=session_id,
            user_text=query
        )

        self.assertEqual(result["detected_language"], "en")
        self.assertEqual(result["extracted_attributes"].get("annual_income"), 150000.0)
        scheme_ids = [s["scheme_id"] for s in result["eligible_schemes"]]
        self.assertIn("ayushman_bharat", scheme_ids)

    async def test_hindi_pm_kisan_flow(self):
        """Tests Hindi Devanagari query for agriculture/farmer welfare."""
        session_id = "test_orch_hindi"
        query = "मैं एक किसान हूँ, मुझे सरकारी योजना की जानकारी चाहिए"

        result = await orchestrator.handle_user_input(
            session_id=session_id,
            user_text=query
        )

        self.assertEqual(result["detected_language"], "hi")
        self.assertEqual(result["extracted_attributes"].get("occupation"), "Farmer")


if __name__ == "__main__":
    unittest.main()
