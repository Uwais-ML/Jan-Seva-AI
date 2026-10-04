"""
Central Agent Orchestrator for Citizen Welfare & Employment Voice Assistant.
Implements the end-to-end loop: STT -> Language Detection -> Demographic Extraction ->
Deterministic Rules Engine -> Grounded RAG Retrieval -> Multilingual Response -> Streaming TTS.
"""

import sys
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, AsyncGenerator

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from RAG.Query_writer import detect_language, extract_user_attributes
from RAG.Retrival import Retrival
from Database.session import SessionLocal
from Database.rules_engine import EligibilityRulesEngine, SchemeMatchResult
from STT.stt_engine import STTEngine
from STT.TTS.tts_engine import TTSEngine
from Backend.session_manager import UserSession, session_registry

logger = logging.getLogger(__name__)


class AgentOrchestrator:
    """
    Coordinates multilingual speech, grounded RAG retrieval, and deterministic eligibility.
    """

    def __init__(self):
        self.rag = Retrival()
        self.stt = STTEngine()
        self.tts = TTSEngine()

    async def handle_user_input(
        self,
        session_id: str,
        user_text: str,
        audio_bytes: Optional[bytes] = None
    ) -> Dict[str, Any]:
        """
        Processes a single user turn:
        1. Transcribe audio if provided, else use user_text
        2. Detect language (Rule 4.B)
        3. Extract demographic data deterministically (Rule 4.D)
        4. Query Rules Engine if user asks about eligibility or provides demographics
        5. Query RAG for knowledge base grounding (Rule 4.C)
        6. Compose proactive, dialect-matching response (Rule 7)
        """
        session = session_registry.get_or_create(session_id)
        session.reset_interruption()

        # 1. Speech-to-Text if raw audio was sent
        if audio_bytes and len(audio_bytes) > 0:
            stt_result = await self.stt.transcribe_audio_bytes(audio_bytes)
            if stt_result.get("transcript"):
                user_text = stt_result["transcript"]

        clean_input = user_text.strip()
        if not clean_input:
            return {
                "response": "I didn't catch that, could you please repeat?",
                "detected_language": "en",
                "extracted_attributes": {},
                "eligible_schemes": [],
                "sources": []
            }

        # 2. Detect Language
        detected_lang = detect_language(clean_input)

        # 3. Deterministic Entity Extraction
        extracted_attrs = extract_user_attributes(clean_input)
        if extracted_attrs:
            session.update_attributes(extracted_attrs)

        # Log user message
        session.add_message("user", clean_input, detected_lang)

        # 4. Check Eligibility via Rules Engine
        eligible_schemes: List[SchemeMatchResult] = []
        with SessionLocal() as db:
            rules_engine = EligibilityRulesEngine(db)
            all_matches = rules_engine.check_all_schemes(session.attributes)
            eligible_schemes = [m for m in all_matches if m.is_eligible][:4]
            if session.attributes:
                rules_engine.save_evaluation(session_id, eligible_schemes)

        # 5. RAG Retrieval with Strict Grounding + multi-turn history
        # Pass last N conversation turns so Groq understands context
        history_for_llm = [
            {"role": turn["role"], "content": turn["content"]}
            for turn in session.history[-8:]   # last 4 exchanges
            if turn.get("role") in ("user", "assistant") and turn.get("content")
        ]

        rag_result = self.rag.get_grounded_answer(
            query=clean_input,
            user_demographics=session.attributes,
            language=detected_lang,
            conversation_history=history_for_llm
        )

        base_answer = rag_result["answer"]
        sources = rag_result["sources"]

        # 6. Proactive Eligibility Augmentation — natural, not a formatted list
        response_text = base_answer
        eligibility_keywords = ["eligible", "patra", "mil sakti", "apply", "qualify", "mera", "milega", "milegi", "benefit"]
        if eligible_schemes and any(k in clean_input.lower() for k in eligibility_keywords):
            top_schemes = eligible_schemes[:2]
            if detected_lang == "hi":
                names = " और ".join([s.scheme_name for s in top_schemes])
                extra = f" वैसे, आपकी जानकारी देखकर लगता है कि {names} के लिए आप eligible हो सकते हैं — क्या इनके बारे में और जानना चाहेंगे?"
            elif detected_lang == "hinglish":
                names = " aur ".join([s.scheme_name for s in top_schemes])
                extra = f" Aur sun, tumhari profile dekh ke lagta hai ki {names} ke liye tum qualify kar sakte ho — kya main aur detail bataun?"
            else:
                names = " and ".join([s.scheme_name for s in top_schemes])
                extra = f" By the way, looking at your profile, you might actually qualify for {names} — want me to walk you through those?"
            response_text += extra

        # Log assistant message
        session.add_message("assistant", response_text, detected_lang, sources=sources)

        return {
            "response": response_text,
            "detected_language": detected_lang,
            "extracted_attributes": session.attributes,
            "eligible_schemes": [
                {
                    "scheme_id": s.scheme_id,
                    "scheme_name": s.scheme_name,
                    "category": s.category,
                    "is_eligible": s.is_eligible,
                    "match_score": s.match_score,
                    "matched_criteria": s.matched_criteria,
                    "benefits": s.benefits,
                    "portal_url": s.portal_url
                }
                for s in eligible_schemes
            ],
            "sources": sources
        }

    async def stream_audio_response(
        self,
        text: str,
        language: str,
        session_id: str
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Streams audio chunks directly for low-latency WebSocket playback.
        Listens to session interruption events to halt streaming immediately.
        """
        session = session_registry.get_or_create(session_id)
        async for chunk in self.tts.stream_text_to_audio_chunks(
            text=text,
            language=language,
            interruption_flag=session.interruption_event
        ):
            yield chunk


orchestrator = AgentOrchestrator()
