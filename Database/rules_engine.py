"""
Deterministic Rules Engine for Indian Citizen Welfare Schemes.
Adheres strictly to Rule 4.D: All math, threshold comparisons, and eligibility criteria
are computed deterministically without relying on LLM arithmetic.
"""

import sys
from pathlib import Path
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from sqlalchemy.orm import Session
from Database.models import SchemeModel, UserProfileModel, EligibilityCheckModel


@dataclass
class SchemeMatchResult:
    scheme_id: str
    scheme_name: str
    category: str
    is_eligible: bool
    match_score: float  # 0.0 to 1.0 based on criteria met
    matched_criteria: List[str] = field(default_factory=list)
    unmatched_criteria: List[str] = field(default_factory=list)
    portal_url: str = ""
    benefits: str = ""
    summary: str = ""


class EligibilityRulesEngine:
    """Evaluates citizen attributes against government scheme rules deterministically."""

    def __init__(self, db: Session):
        self.db = db

    def evaluate_scheme(self, user_data: Dict[str, Any], scheme: SchemeModel) -> SchemeMatchResult:
        """Evaluates a single scheme against user profile attributes."""
        matched = []
        unmatched = []
        is_eligible = True
        total_checks = 0
        passed_checks = 0

        # 1. Age check
        user_age = user_data.get("age")
        if user_age is not None:
            total_checks += 1
            if scheme.min_age <= user_age <= scheme.max_age:
                matched.append(f"Age {user_age} is within eligible range ({scheme.min_age}-{scheme.max_age} years)")
                passed_checks += 1
            else:
                unmatched.append(f"Age {user_age} is outside eligible range ({scheme.min_age}-{scheme.max_age} years)")
                is_eligible = False

        # 2. Income check (annual or monthly * 12)
        annual_income = user_data.get("annual_income")
        if annual_income is None and user_data.get("monthly_income") is not None:
            annual_income = user_data["monthly_income"] * 12

        if scheme.max_annual_income is not None:
            total_checks += 1
            if annual_income is not None:
                if annual_income <= scheme.max_annual_income:
                    matched.append(f"Annual income ₹{annual_income:,.0f} is within limit of ₹{scheme.max_annual_income:,.0f}")
                    passed_checks += 1
                else:
                    unmatched.append(f"Annual income ₹{annual_income:,.0f} exceeds maximum threshold of ₹{scheme.max_annual_income:,.0f}")
                    is_eligible = False
            else:
                # Income not specified yet, treat as pending
                pass

        # 3. State check
        user_state = user_data.get("state")
        eligible_states = scheme.eligible_states or ["All"]
        if "All" not in eligible_states and user_state:
            total_checks += 1
            normalized_user_state = user_state.strip().lower()
            allowed = [s.strip().lower() for s in eligible_states]
            if normalized_user_state in allowed:
                matched.append(f"State '{user_state}' is eligible")
                passed_checks += 1
            else:
                unmatched.append(f"Scheme is not applicable in state '{user_state}'")
                is_eligible = False

        # 4. Gender restriction check
        user_gender = user_data.get("gender")
        if scheme.gender_restriction and scheme.gender_restriction != "Any" and user_gender:
            total_checks += 1
            if scheme.gender_restriction.lower() == user_gender.strip().lower():
                matched.append(f"Gender matches criteria: {scheme.gender_restriction}")
                passed_checks += 1
            else:
                unmatched.append(f"Scheme is restricted to {scheme.gender_restriction} beneficiaries")
                is_eligible = False

        # 5. Occupation check
        user_occ = user_data.get("occupation")
        eligible_occs = scheme.eligible_occupations or []
        if eligible_occs and "All" not in eligible_occs and user_occ:
            total_checks += 1
            user_occ_lower = user_occ.strip().lower()
            match_occ = any(user_occ_lower in occ.lower() or occ.lower() in user_occ_lower for occ in eligible_occs)
            if match_occ:
                matched.append(f"Occupation '{user_occ}' matches target beneficiaries ({', '.join(eligible_occs)})")
                passed_checks += 1
            else:
                unmatched.append(f"Occupation '{user_occ}' not in target groups ({', '.join(eligible_occs)})")
                is_eligible = False

        # Calculate score
        if total_checks > 0:
            score = round(passed_checks / total_checks, 2)
        else:
            score = 0.5  # Neutral when no demographics specified

        summary_parts = []
        if is_eligible and total_checks > 0:
            summary_parts.append(f"Eligible ({int(score * 100)}% criteria match)")
        elif not is_eligible:
            summary_parts.append("Not Eligible currently")
        else:
            summary_parts.append("Potential match (details pending)")

        return SchemeMatchResult(
            scheme_id=scheme.scheme_id,
            scheme_name=scheme.name,
            category=scheme.category,
            is_eligible=is_eligible,
            match_score=score,
            matched_criteria=matched,
            unmatched_criteria=unmatched,
            portal_url=scheme.portal_url or "",
            benefits=scheme.benefits or "",
            summary="; ".join(summary_parts)
        )

    def check_all_schemes(self, user_data: Dict[str, Any]) -> List[SchemeMatchResult]:
        """Evaluates all schemes in the database and returns ranked results."""
        schemes = self.db.query(SchemeModel).all()
        results = [self.evaluate_scheme(user_data, scheme) for scheme in schemes]

        # Sort: eligible first, then by match score descending
        results.sort(key=lambda r: (r.is_eligible, r.match_score), reverse=True)
        return results

    def save_evaluation(self, session_id: str, results: List[SchemeMatchResult]) -> None:
        """Persists evaluation results to DB for historical and follow-up tracking."""
        for r in results:
            check = EligibilityCheckModel(
                session_id=session_id,
                scheme_id=r.scheme_id,
                scheme_name=r.scheme_name,
                is_eligible=r.is_eligible,
                match_score=r.match_score,
                matched_criteria=r.matched_criteria,
                unmatched_criteria=r.unmatched_criteria,
                reasons=r.summary
            )
            self.db.add(check)
        self.db.commit()
