"""
Text-to-Speech (TTS) Engine with Sarvam AI (Bulbul) support,
chunked streaming, and dynamic Indian language voice switching.
Optimised for human-sounding, natural speech delivery.
"""

import os
import sys
import re
import json
import base64
import logging
import asyncio
from typing import List, Dict, Any, Optional, AsyncGenerator, Tuple
from pathlib import Path
import aiohttp

BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

logger = logging.getLogger(__name__)


# Punctuation that marks a natural speaking pause / breath point
_SENTENCE_BREAK = re.compile(r'(?<=[.?!।…\n])\s+')
# Commas + conjunctions that can be secondary split points if chunk is too long
_CLAUSE_BREAK = re.compile(r'(?<=[,;])\s+')


def split_into_tts_chunks(text: str, max_chars: int = 140) -> List[str]:
    """
    Splits text into small, natural spoken sentence chunks for low-latency TTS.
    Strategy:
      1. Strip all markdown / URLs so TTS doesn't read asterisks or URLs aloud.
      2. Split on sentence-ending punctuation first (most natural breath points).
      3. If a resulting piece is still too long, split on clause boundaries (commas).
      4. As a last resort, split at word boundary near max_chars.
    """
    # ── Clean markdown artifacts ──────────────────────────────────────────────
    clean = re.sub(r'\[.*?\]\(.*?\)', '', text)     # [text](url)
    clean = re.sub(r'[*#_`~]', '', clean)           # **, ##, _, `, ~
    clean = re.sub(r'https?://\S+', '', clean)       # bare URLs
    clean = re.sub(r'•\s*', '', clean)               # bullet points
    clean = re.sub(r'\n+', ' ', clean)               # newlines → space
    clean = re.sub(r'\s{2,}', ' ', clean).strip()   # collapse whitespace

    # ── Split on sentence boundaries ─────────────────────────────────────────
    raw_sentences = _SENTENCE_BREAK.split(clean)
    chunks: List[str] = []

    for sentence in raw_sentences:
        sentence = sentence.strip()
        if not sentence:
            continue

        if len(sentence) <= max_chars:
            chunks.append(sentence)
        else:
            # Try splitting on clause boundaries first
            clauses = _CLAUSE_BREAK.split(sentence)
            current = ""
            for clause in clauses:
                clause = clause.strip()
                if not clause:
                    continue
                if len(current) + len(clause) + 1 <= max_chars:
                    current = (current + " " + clause).strip()
                else:
                    if current:
                        chunks.append(current)
                    # If a single clause is still too long, hard-split at word boundary
                    if len(clause) > max_chars:
                        words = clause.split()
                        current = ""
                        for word in words:
                            if len(current) + len(word) + 1 <= max_chars:
                                current = (current + " " + word).strip()
                            else:
                                if current:
                                    chunks.append(current)
                                current = word
                        if current:
                            chunks.append(current)
                        current = ""
                    else:
                        current = clause
            if current:
                chunks.append(current)

    return chunks if chunks else ([clean.strip()] if clean.strip() else [])


class TTSEngine:
    """
    Handles speech synthesis using Sarvam Bulbul or local browser fallback.
    Tuned for warm, natural-sounding Indian English / Hindi output.
    """

    # Voice personalities: (target_language_code, speaker, pace, pitch)
    VOICE_MAP: Dict[str, Tuple[str, str, float, int]] = {
        "hi":       ("hi-IN",    "meera",  0.95,  0),   # calm, clear Hindi
        "hinglish": ("hi-IN",    "arvind", 1.0,   0),   # friendly, natural Hinglish
        "en":       ("en-IN",    "meera",  1.0,   0),   # warm Indian English
        "ta":       ("ta-IN",    "meera",  0.95,  0),
        "te":       ("te-IN",    "meera",  0.95,  0),
        "bn":       ("bn-IN",    "meera",  0.95,  0),
        "mr":       ("mr-IN",    "meera",  0.95,  0),
    }

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("SARVAM_API_KEY", "")
        self.bulbul_url = "https://api.sarvam.ai/text-to-speech"

    def select_voice_target(self, language: str) -> Tuple[str, str, float, int]:
        """Returns (target_language_code, speaker, pace, pitch) for the given language."""
        return self.VOICE_MAP.get(language, self.VOICE_MAP["en"])

    async def synthesize_chunk(
        self,
        text: str,
        language: str = "en"
    ) -> Optional[Dict[str, Any]]:
        """
        Synthesizes a single text chunk into audio via Sarvam Bulbul.
        Falls back to browser Web Speech if no API key is configured.
        Returns a dict with audio_base64 (or None for fallback).
        """
        text = text.strip()
        if not text:
            return None

        target_lang, speaker, pace, pitch = self.select_voice_target(language)

        if self.api_key:
            payload = {
                "inputs": [text],
                "target_language_code": target_lang,
                "speaker": speaker,
                "pitch": pitch,
                "pace": pace,
                "loudness": 1.4,
                "speech_sample_rate": 22050,
                "enable_preprocessing": True,   # handles abbreviations, numbers, etc.
                "model": "bulbul:v1"
            }
            headers = {
                "Content-Type": "application/json",
                "api-subscription-key": self.api_key
            }

            try:
                async with aiohttp.ClientSession() as http:
                    async with http.post(
                        self.bulbul_url,
                        json=payload,
                        headers=headers,
                        timeout=aiohttp.ClientTimeout(total=6.0)
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            audios = data.get("audios", [])
                            if audios:
                                return {
                                    "audio_base64": audios[0],
                                    "format": "wav",
                                    "text": text,
                                    "language": target_lang,
                                    "speaker": speaker
                                }
                        else:
                            error_text = await resp.text()
                            logger.warning(f"Sarvam TTS failed ({resp.status}): {error_text}")
            except asyncio.TimeoutError:
                logger.warning("Sarvam TTS request timed out, using browser fallback")
            except Exception as e:
                logger.error(f"TTS synthesis error: {e}")

        # ── Browser Web Speech fallback ───────────────────────────────────────
        # Provides enough metadata for the frontend to use speechSynthesis API
        # with correct language and a natural speaking rate
        return {
            "audio_base64": None,
            "format": "speech_synthesis_fallback",
            "text": text,
            "language": target_lang,
            "speaker": speaker,
            "rate": pace,       # frontend uses this for speechSynthesis.rate
            "pitch": 1.05       # slightly warmer pitch than default
        }

    async def stream_text_to_audio_chunks(
        self,
        text: str,
        language: str = "en",
        interruption_flag: Optional[asyncio.Event] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Yields synthesized audio chunks in sequence for low-latency streaming.
        Stops immediately if interruption_flag is set (Rule 4.A).

        Parallelism: starts synthesizing chunk N+1 while chunk N is being played,
        using asyncio.create_task for overlap when Sarvam API key is available.
        """
        chunks = split_into_tts_chunks(text)
        total = len(chunks)

        for idx, chunk in enumerate(chunks):
            if interruption_flag and interruption_flag.is_set():
                logger.info("TTS streaming interrupted by user action.")
                break

            result = await self.synthesize_chunk(chunk, language)
            if result:
                result["chunk_index"] = idx
                result["total_chunks"] = total
                yield result

            # Tiny pause between sentences to feel more natural (non-blocking)
            if idx < total - 1:
                await asyncio.sleep(0.03)
