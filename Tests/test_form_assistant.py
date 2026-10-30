"""
Tests for the Official Form-Filling Assistant ("Form Sahayak").
"""

import sys
import unittest
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from Database.session import init_db, SessionLocal
from Database.models import ApplicationSubmissionModel
from Backend.session_manager import session_registry
from Backend.form_filling_agent import form_agent


class TestFormAssistant(unittest.TestCase):

    def setUp(self):
        init_db()
        self.session_id = "test_form_session_1"
        session_registry.reset_session(self.session_id)
        self.session = session_registry.get_or_create(self.session_id)
        self.session.attributes = {}
        self.session.active_form = None

    def test_start_form_pmkvy(self):
        """Test starting a form fills known demographic attributes and prompts for the next field."""
        self.session.attributes["age"] = 22
        res = form_agent.start_form(self.session, "PMKVY ka form bhar do", "hinglish")
        
        self.assertTrue(res["is_active"])
        self.assertIsNotNone(self.session.active_form)
        self.assertEqual(self.session.active_form["scheme_id"], "pmkvy")
        # Age should be pre-filled
        self.assertEqual(self.session.active_form["fields"]["age"]["value"], 22)
        self.assertEqual(self.session.active_form["fields"]["age"]["status"], "completed")

    def test_full_form_lifecycle_and_submission(self):
        """Test full turn-by-turn field answers, confirmation, and DB persistence."""
        # 1. Start form
        form_agent.start_form(self.session, "I want to apply for PMKVY", "en")
        
        # 2. Answer full name
        res = form_agent.process_turn(self.session, "My name is Rajesh Verma", "en")
        self.assertEqual(self.session.active_form["fields"]["full_name"]["value"], "Rajesh Verma")

        # 3. Answer mobile
        res = form_agent.process_turn(self.session, "9876543210", "en")
        self.assertEqual(self.session.active_form["fields"]["mobile"]["value"], "9876543210")

        # 4. Answer age
        res = form_agent.process_turn(self.session, "24", "en")
        self.assertEqual(self.session.active_form["fields"]["age"]["value"], 24)

        # 5. Answer qualification
        res = form_agent.process_turn(self.session, "Graduate in Commerce", "en")
        self.assertEqual(self.session.active_form["fields"]["qualification"]["value"], "Graduate in Commerce")

        # 6. Answer course
        res = form_agent.process_turn(self.session, "Solar Panel Technician Course", "en")
        self.assertEqual(self.session.active_form["fields"]["course_interest"]["value"], "Solar Panel Technician Course")

        # 7. Answer state & district
        res = form_agent.process_turn(self.session, "Lucknow, Uttar Pradesh", "en")
        self.assertEqual(self.session.active_form["fields"]["state_district"]["value"], "Lucknow, Uttar Pradesh")

        # Now all fields should be filled and awaiting confirmation
        self.assertTrue(res["form_state"]["awaiting_confirmation"])
        self.assertEqual(res["form_state"]["progress_percentage"], 100)

        # 8. Confirm submit
        submit_res = form_agent.process_turn(self.session, "Yes, please submit", "en")
        self.assertTrue(submit_res["is_submitted"])
        self.assertIsNotNone(submit_res["application_ref"])
        self.assertTrue(submit_res["application_ref"].startswith("PMKVY-2026-IND-"))

        # 9. Verify in database
        with SessionLocal() as db:
            sub = db.query(ApplicationSubmissionModel).filter_by(application_ref=submit_res["application_ref"]).first()
            self.assertIsNotNone(sub)
            self.assertEqual(sub.scheme_id, "pmkvy")
            self.assertEqual(sub.form_data["full_name"], "Rajesh Verma")
            self.assertEqual(sub.form_data["mobile"], "9876543210")


if __name__ == "__main__":
    unittest.main()
