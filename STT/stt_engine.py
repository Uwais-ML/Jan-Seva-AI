"""
Speech-to-Text (STT) Engine with Sarvam AI (Saarika) support,
multilingual language detection, and audio chunk handling.
"""

import os
import sys
import json
import logging
import asyncio
from typing import Dict, Any, Optional, Tuple
from pathlib import Path
import aiohttp

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from RAG.Query_writer import detect_language

logger = logging.getLogger(__name__)


class STTEngine:
    """
    Handles speech transcription and real-time audio chunk decoding.
    Supports Sarvam AI Saarika API with local / browser audio bridge fallback.
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("SARVAM_API_KEY", "")
        self.saarika_url = "https://api.sarvam.ai/speech-to-text"

    async def transcribe_audio_bytes(
        self,
        audio_bytes: bytes,
        mime_type: str = "audio/wav",
        language_code: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Transcribes audio bytes to text and detects spoken language.
        If Sarvam API key is available, calls Saarika v1.
        Otherwise provides a clear error or processes client metadata.
        """
        if self.api_key:
            try:
                data = aiohttp.FormData()
                data.add_field(
                    "file",
                    audio_bytes,
                    filename="audio.wav",
                    content_type=mime_type
                )
                if language_code:
                    data.add_field("language_code", language_code)
                else:
                    data.add_field("language_code", "unknown")  # auto-detect
                data.add_field("model", "saarika:v1")

                headers = {"api-subscription-key": self.api_key}
                async with aiohttp.ClientSession() as session:
                    async with session.post(self.saarika_url, data=data, headers=headers, timeout=5.0) as resp:
                        if resp.status == 200:
                            result = await resp.json()
                            transcript = result.get("transcript", "").strip()
                            detected_lang = result.get("language_code", "en-IN")
                            norm_lang = "hi" if "hi" in detected_lang else "en"
                            return {
                                "transcript": transcript,
                                "language": norm_lang,
                                "raw_language": detected_lang,
                                "confidence": result.get("confidence", 1.0)
                            }
                        else:
                            error_text = await resp.text()
                            logger.warning(f"Sarvam STT failed with status {resp.status}: {error_text}")
            except Exception as e:
                logger.error(f"Error during Sarvam STT call: {e}")

        # Fallback when no Sarvam API key is present:
        # Handled seamlessly via Web Speech API or client transcript forwarding
        return {
            "transcript": "",
            "language": "en",
            "error": "No STT API key provided or audio buffer unrecognized"
        }

    def process_transcript(self, raw_text: str) -> Dict[str, Any]:
        """
        Processes incoming text or transcript string, classifying language dynamically.
        """
        clean_text = raw_text.strip()
        lang = detect_language(clean_text)
        return {
            "transcript": clean_text,
            "language": lang
        }
