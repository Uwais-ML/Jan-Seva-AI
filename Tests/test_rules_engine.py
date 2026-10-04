"""
Unit tests for the Deterministic Rules Engine (Rule 4.D).
Tests edge cases, boundary conditions, and eligibility rules.
"""

import sys
import unittest
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from Database.session import SessionLocal, init_db
from Database.rules_engine import EligibilityRulesEngine
from Database.models import SchemeModel


class TestRulesEngine(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        init_db()
        cls.db = SessionLocal()
        cls.engine = EligibilityRulesEngine(cls.db)

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def test_pmkvy_eligible_candidate(self):
        """User aged 22, unemployed should be eligible for PMKVY."""
        user = {"age": 22, "occupation": "Unemployed"}
        results = self.engine.check_all_schemes(user)
        pmkvy = next((r for r in results if r.scheme_id == "pmkvy"), None)
        self.assertIsNotNone(pmkvy)
        self.assertTrue(pmkvy.is_eligible)
        self.assertGreater(pmkvy.match_score, 0.5)

    def test_pmkvy_ineligible_due_to_age(self):
        """User aged 55 is above the 15-45 age limit for PMKVY."""
        user = {"age": 55, "occupation": "Unemployed"}
        results = self.engine.check_all_schemes(user)
        pmkvy = next((r for r in results if r.scheme_id == "pmkvy"), None)
        self.assertIsNotNone(pmkvy)
        self.assertFalse(pmkvy.is_eligible)
        self.assertTrue(any("outside eligible range" in u for u in pmkvy.unmatched_criteria))

    def test_ayushman_bharat_income_ceiling(self):
        """Ayushman Bharat max annual income is 2,50,000."""
        # Low income candidate:
        user_eligible = {"annual_income": 180000.0}
        res_el = self.engine.check_all_schemes(user_eligible)
        ab_el = next((r for r in res_el if r.scheme_id == "ayushman_bharat"), None)
        self.assertTrue(ab_el.is_eligible)

        # High income candidate:
        user_ineligible = {"annual_income": 500000.0}
        res_inel = self.engine.check_all_schemes(user_ineligible)
        ab_inel = next((r for r in res_inel if r.scheme_id == "ayushman_bharat"), None)
        self.assertFalse(ab_inel.is_eligible)
        self.assertTrue(any("exceeds maximum threshold" in u for u in ab_inel.unmatched_criteria))

    def test_sukanya_samriddhi_age_limit(self):
        """Sukanya Samriddhi is only for girl child aged <= 10."""
        user_young = {"age": 6, "gender": "Female"}
        res_young = self.engine.check_all_schemes(user_young)
        ssy_young = next((r for r in res_young if r.scheme_id == "sukanya_samriddhi"), None)
        self.assertTrue(ssy_young.is_eligible)

        user_old = {"age": 16, "gender": "Female"}
        res_old = self.engine.check_all_schemes(user_old)
        ssy_old = next((r for r in res_old if r.scheme_id == "sukanya_samriddhi"), None)
        self.assertFalse(ssy_old.is_eligible)

    def test_monthly_to_annual_conversion(self):
        """Rules engine should automatically handle monthly income * 12."""
        # 15,000 monthly = 180,000 annual (within 250,000)
        user = {"monthly_income": 15000.0}
        results = self.engine.check_all_schemes(user)
        ab = next((r for r in results if r.scheme_id == "ayushman_bharat"), None)
        self.assertTrue(ab.is_eligible)


if __name__ == "__main__":
    unittest.main()
