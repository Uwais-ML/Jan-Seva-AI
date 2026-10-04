"""
Database models for Citizen Profiles, Government Schemes, and Session History.
"""

from datetime import datetime
from typing import Optional, List
from sqlalchemy import Column, Integer, String, Float, Boolean, Text, DateTime, ForeignKey, JSON
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class SchemeModel(Base):
    """Stores master data and strict eligibility criteria for Indian Government Schemes."""
    __tablename__ = "schemes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    scheme_id = Column(String(64), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    category = Column(String(100), nullable=False, index=True)
    description = Column(Text, nullable=False)
    
    # Eligibility boundary rules
    min_age = Column(Integer, default=0)
    max_age = Column(Integer, default=120)
    max_annual_income = Column(Float, nullable=True)  # None indicates no explicit income cap
    eligible_occupations = Column(JSON, default=list)  # ["Farmer", "Unemployed", etc.]
    eligible_states = Column(JSON, default=lambda: ["All"])
    eligible_education = Column(JSON, default=lambda: ["Any"])
    gender_restriction = Column(String(32), default="Any")  # "Any", "Female", "Male"
    
    benefits = Column(Text, nullable=False)
    portal_url = Column(String(255), nullable=True)
    tags = Column(JSON, default=list)
    created_at = Column(DateTime, default=datetime.utcnow)


class UserProfileModel(Base):
    """Maintains structured demographic attributes extracted for a user session."""
    __tablename__ = "user_profiles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(128), unique=True, nullable=False, index=True)
    age = Column(Integer, nullable=True)
    annual_income = Column(Float, nullable=True)
    monthly_income = Column(Float, nullable=True)
    education_level = Column(String(64), nullable=True)
    state = Column(String(64), nullable=True)
    occupation = Column(String(64), nullable=True)
    gender = Column(String(32), nullable=True)
    social_category = Column(String(32), nullable=True)  # General, OBC, SC, ST, EWS
    is_landholder = Column(Boolean, nullable=True)
    preferred_language = Column(String(32), default="en")
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    eligibility_checks = relationship("EligibilityCheckModel", back_populates="user", cascade="all, delete-orphan")


class EligibilityCheckModel(Base):
    """Historical record of eligibility runs evaluated via the deterministic rules engine."""
    __tablename__ = "eligibility_checks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(128), ForeignKey("user_profiles.session_id"), nullable=False, index=True)
    scheme_id = Column(String(64), nullable=False)
    scheme_name = Column(String(255), nullable=False)
    is_eligible = Column(Boolean, nullable=False)
    match_score = Column(Float, default=0.0)  # 0.0 to 1.0
    matched_criteria = Column(JSON, default=list)
    unmatched_criteria = Column(JSON, default=list)
    reasons = Column(Text, nullable=True)
    evaluated_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("UserProfileModel", back_populates="eligibility_checks")


class ConversationLogModel(Base):
    """Audit log of user dialogue turns with detected language and sources."""
    __tablename__ = "conversation_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(128), nullable=False, index=True)
    role = Column(String(32), nullable=False)  # user / assistant / system
    content = Column(Text, nullable=False)
    detected_language = Column(String(32), nullable=True)  # en, hi, hinglish
    sources = Column(JSON, default=list)  # cited sources / portals
    audio_latency_ms = Column(Float, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
