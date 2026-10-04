"""
RAG Retrieval & Grounded Generation for Indian Citizen Welfare Schemes.
Adheres strictly to Rule 4.C: Strict Grounding, Source Citation, and Demographic Prioritization.
Powered by Groq (qwen/qwen3.8-27b) with true streaming support.
"""

import os
import sys
import re
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, AsyncGenerator

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from RAG.Query_writer import Query_writer, detect_language
from RAG.Indegstion import KnowledgeIndexer, KnowledgeBaseChunk

logger = logging.getLogger(__name__)


class GroundedRetriever:
    """Retrieves and ranks relevant knowledge chunks with demographic awareness."""

    def __init__(self):
        self.indexer = KnowledgeIndexer()
        if not self.indexer.chunks:
            self.indexer.ingest_documents()

    def search(
        self,
        query: str,
        user_demographics: Optional[Dict[str, Any]] = None,
        top_k: int = 4
    ) -> List[KnowledgeBaseChunk]:
        if not self.indexer.chunks:
            return []

        STOP_WORDS = {
            "how", "what", "when", "where", "which", "who", "whom", "this", "that",
            "with", "from", "have", "been", "will", "would", "could", "should", "there",
            "their", "they", "does", "done", "about", "into", "give", "tell", "show",
            "want", "need", "like", "with", "recipe", "cook", "cooking", "pizza"
        }
        cleaned = re.sub(r"[^\w\s]", " ", query.lower())
        tokens = [t for t in cleaned.split() if len(t) > 2 and t not in STOP_WORDS]
        if not tokens:
            return []

        user_demographics = user_demographics or {}
        user_state = user_demographics.get("state", "").lower()
        user_occ = user_demographics.get("occupation", "").lower()

        scored: List[Tuple[float, KnowledgeBaseChunk]] = []
        for chunk in self.indexer.chunks:
            content_words = set(re.findall(r"\b\w+\b", chunk.content.lower()))
            title_words  = set(re.findall(r"\b\w+\b", chunk.title.lower()))
            score = 0.0

            for t in tokens:
                if t in title_words:
                    score += 5.0
                elif t in content_words:
                    score += 1.0

            for tag in chunk.metadata.get("tags", []):
                tag_words = set(re.findall(r"\b\w+\b", tag.lower()))
                if any(t in tag_words for t in tokens):
                    score += 4.0

            if user_state and user_state in content_words:
                score += 2.0
            if user_occ and user_occ in content_words:
                score += 2.5

            if score >= 4.0:
                scored.append((score, chunk))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [c for _, c in scored[:top_k]]


class Retrival:
    """
    Main RAG pipeline with true streaming support.
    stream_grounded_answer() yields text tokens as they arrive from Groq —
    the server can pipe them straight to TTS sentence-by-sentence.
    """

    def __init__(self, query_writer_url: Optional[str] = None):
        self.base_url = query_writer_url or os.getenv("OPENAI_BASE_URL", "https://api.groq.com/openai/v1")
        self.api_key  = os.getenv("OPENAI_API_KEY", "")
        self.model    = os.getenv("DEFAULT_LLM_MODEL", "qwen/qwen3.8-27b")
        self.query_writer = Query_writer(api_key=self.api_key, url=self.base_url)
        self.retriever    = GroundedRetriever()

    # ──────────────────────────────────────────────────────────────────────────
    # INTERNAL HELPERS
    # ──────────────────────────────────────────────────────────────────────────

    def _build_context(
        self,
        query: str,
        user_demographics: Optional[Dict],
        conversation_history: Optional[List[Dict[str, str]]] = None
    ) -> Tuple[List[KnowledgeBaseChunk], str, List[str]]:
        """Normalize query, retrieve chunks, build context string and sources list."""
        try:
            trans_resp = self.query_writer.write_qwery(query, conversation_history)
            if hasattr(trans_resp, "choices") and trans_resp.choices:
                search_query = trans_resp.choices[0].message.content.strip()
            else:
                search_query = self.query_writer.normalize_query_offline(query, conversation_history)
        except Exception:
            search_query = self.query_writer.normalize_query_offline(query, conversation_history)

        chunks = self.retriever.search(search_query, user_demographics=user_demographics, top_k=3)

        context_parts, sources = [], set()
        for idx, c in enumerate(chunks, 1):
            src = c.metadata.get("source", "Government Records")
            portal = c.metadata.get("portal_url")
            sources.add(f"{src} ({portal})" if portal else src)
            context_parts.append(f"[{idx}] {c.title}\n{c.content}")

        return chunks, "\n\n".join(context_parts), sorted(list(sources))

    def _build_messages(
        self,
        query: str,
        context: str,
        language: str,
        conversation_history: List[Dict[str, str]]
    ) -> List[Dict[str, str]]:
        lang_instruction = {
            "hi":       "हिंदी में बात करो — बिल्कुल बोलचाल के अंदाज़ में, जैसे दोस्त बात करता है।",
            "hinglish": "Hinglish mein baat karo — English aur Hindi ka natural mix, jaise real life mein baat karte hain.",
            "en":       "Speak in warm, natural Indian English — like a knowledgeable friend, not a call centre script."
        }.get(language, "Reply in natural conversational English.")

        system = (
            "You are Sahayak, a warm and caring AI voice assistant helping Indian citizens "
            "understand government welfare schemes. You speak like a knowledgeable dost (friend).\n\n"
            "PERSONALITY:\n"
            "- Natural, warm, conversational — like a helpful bhaiya/didi\n"
            "- Proactive — always offer the next step\n"
            "- You remember what was said earlier in the conversation\n"
            "- You understand partial sentences, accents, and Hinglish\n\n"
            "STRICT RULES:\n"
            "1. Use ONLY the provided Context. Never invent facts or numbers.\n"
            "2. NO markdown: no **bold**, no bullet points, no ## headers. Pure spoken sentences.\n"
            "3. Keep it SHORT: 3–5 sentences maximum. This plays as audio.\n"
            "4. End with ONE natural follow-up question or offer to help.\n"
            "5. If context is missing, say so naturally and offer a related topic.\n"
            f"6. {lang_instruction}"
        )

        messages = [{"role": "system", "content": system}]

        # Last 6 turns of history for multi-turn awareness
        for turn in (conversation_history or [])[-6:]:
            role = turn.get("role", "")
            content = turn.get("content", "")
            if content and role in ("user", "assistant"):
                messages.append({"role": role, "content": content})

        messages.append({
            "role": "user",
            "content": f"Context from verified government records:\n{context}\n\nUser said: {query}"
        })
        return messages

    def _not_found_msg(self, language: str) -> str:
        return {
            "hi":       "माफ़ करें, इस बारे में मेरे पास कोई सरकारी जानकारी नहीं है। कोई और सरकारी योजना के बारे में पूछना चाहते हैं?",
            "hinglish": "Yaar, is topic ke baare mein koi verified government info nahi mili. Koi aur scheme ke baare mein poochh sakte ho!",
            "en":       "I'm sorry, I don't have verified government information on that. Is there a specific scheme I can help you with?"
        }.get(language, "I don't have information on that topic.")

    # ──────────────────────────────────────────────────────────────────────────
    # PUBLIC API — BLOCKING (used by tests + REST fallback)
    # ──────────────────────────────────────────────────────────────────────────

    def get_grounded_answer(
        self,
        query: str,
        user_demographics: Optional[Dict[str, Any]] = None,
        language: Optional[str] = None,
        conversation_history: Optional[List[Dict[str, str]]] = None
    ) -> Dict[str, Any]:
        detected_lang = language or detect_language(query)
        chunks, context, sources = self._build_context(query, user_demographics, conversation_history)

        if not chunks:
            return {
                "answer": self._not_found_msg(detected_lang),
                "sources": [],
                "detected_language": detected_lang,
                "retrieved_chunks": 0
            }

        answer = self._generate_answer_blocking(
            query=query,
            context=context,
            language=detected_lang,
            sources=sources,
            conversation_history=conversation_history or []
        )

        return {
            "answer": answer,
            "sources": sources,
            "detected_language": detected_lang,
            "retrieved_chunks": len(chunks)
        }

    def _generate_answer_blocking(
        self,
        query: str,
        context: str,
        language: str,
        sources: List[str],
        conversation_history: List[Dict[str, str]]
    ) -> str:
        messages = self._build_messages(query, context, language, conversation_history)
        if self.query_writer.client:
            try:
                resp = self.query_writer.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=0.65,
                    max_tokens=400,
                    timeout=12.0
                )
                if resp.choices and resp.choices[0].message.content:
                    return resp.choices[0].message.content.strip()
            except Exception as e:
                logger.warning(f"Groq LLM call failed, using offline synthesis: {e}")

        return self._grounded_template_synthesis(query, context, language, sources)

    # ──────────────────────────────────────────────────────────────────────────
    # PUBLIC API — STREAMING (used by WebSocket handler for real-time TTS)
    # ──────────────────────────────────────────────────────────────────────────

    async def stream_grounded_answer(
        self,
        query: str,
        user_demographics: Optional[Dict[str, Any]] = None,
        language: Optional[str] = None,
        conversation_history: Optional[List[Dict[str, str]]] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Async generator that:
        1. Retrieves knowledge chunks (fast, local).
        2. Streams Groq tokens.
        3. Yields complete sentences as {type, text, sources, detected_language, is_final}
           so the WebSocket server can pipe each sentence straight to TTS.

        Falls back to yielding the full template synthesis in one shot.
        """
        detected_lang = language or detect_language(query)
        chunks, context, sources = self._build_context(query, user_demographics, conversation_history)

        # Metadata sent first so frontend can update UI immediately
        meta = {
            "type": "meta",
            "sources": sources,
            "detected_language": detected_lang,
            "retrieved_chunks": len(chunks)
        }

        if not chunks:
            yield {**meta, "type": "sentence", "text": self._not_found_msg(detected_lang), "is_final": True}
            return

        yield meta   # send sources/lang before any text arrives

        messages = self._build_messages(query, context, detected_lang, conversation_history or [])

        # ── Try Groq streaming ────────────────────────────────────────────────
        if self.query_writer.client:
            try:
                stream = self.query_writer.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=0.65,
                    max_tokens=400,
                    stream=True,       # ← KEY: true streaming
                    timeout=15.0
                )

                buffer = ""
                SENTENCE_END = re.compile(r'(?<=[.!?।…])\s+|(?<=\n)')
                full_response = ""

                for chunk_obj in stream:
                    delta = chunk_obj.choices[0].delta.content or ""
                    buffer += delta
                    full_response += delta

                    # Yield each complete sentence as it arrives
                    parts = SENTENCE_END.split(buffer)
                    # Last part is incomplete — keep in buffer
                    for sentence in parts[:-1]:
                        sentence = sentence.strip()
                        if sentence:
                            yield {
                                "type": "sentence",
                                "text": sentence,
                                "is_final": False
                            }
                    buffer = parts[-1]

                # Flush remaining buffer
                if buffer.strip():
                    yield {
                        "type": "sentence",
                        "text": buffer.strip(),
                        "is_final": True
                    }
                else:
                    yield {"type": "sentence", "text": "", "is_final": True}
                return

            except Exception as e:
                logger.warning(f"Groq stream failed, falling back to template: {e}")

        # ── Template synthesis fallback — yield in one shot ───────────────────
        fallback = self._grounded_template_synthesis(query, context, detected_lang, sources)
        # Split fallback into sentences for consistent downstream behaviour
        for sentence in re.split(r'(?<=[.!?।])\s+', fallback):
            if sentence.strip():
                yield {"type": "sentence", "text": sentence.strip(), "is_final": False}
        yield {"type": "sentence", "text": "", "is_final": True}

    # ──────────────────────────────────────────────────────────────────────────
    # OFFLINE FALLBACK
    # ──────────────────────────────────────────────────────────────────────────

    def _grounded_template_synthesis(
        self,
        query: str,
        context: str,
        language: str,
        sources: List[str]
    ) -> str:
        """Natural, conversational offline fallback. No markdown, no bullets."""
        first_chunk = context.split("\n\n")[0]
        lines = [l.strip() for l in first_chunk.split("\n") if l.strip()]

        scheme_name = category = desc = benefits = eligibility = portal = ""
        for line in lines:
            ll = line.lower()
            if line.startswith("Scheme:"):       scheme_name = line.split(":", 1)[1].strip()
            elif line.startswith("Category:"):   category    = line.split(":", 1)[1].strip()
            elif line.startswith("Description:"): desc       = line.split(":", 1)[1].strip()
            elif line.startswith("Benefits:"):   benefits    = line.split(":", 1)[1].strip()
            elif "eligible age" in ll or "eligibility" in ll:
                eligibility = re.sub(r"[*#_\-•]", "", line).strip()
            elif line.startswith("Official Portal:"):
                portal = line.split(":", 1)[1].strip()

        if not scheme_name and lines:
            scheme_name = re.sub(r"[*#_]", "", lines[0]).strip()
        if not desc and len(lines) > 1:
            desc = " ".join([
                re.sub(r"[*#_•]", "", l).strip()
                for l in lines[1:4]
                if not l.startswith("#") and len(l) > 20
            ])[:200]

        source_str = portal or (sources[0].split("(")[-1].rstrip(")") if sources else "the official government portal")

        if language == "hi":
            parts = []
            if scheme_name:
                parts.append(f"{scheme_name} एक बहुत अच्छी सरकारी योजना है{f' जो {category} के लिए है' if category else ''}।")
            if desc:
                parts.append(desc.rstrip(".") + "।")
            if benefits:
                parts.append(f"इसके ज़रिये आपको {benefits} मिल सकता है।")
            if eligibility:
                parts.append(f"{eligibility}।")
            parts.append("क्या मैं आपकी उम्र और आय के हिसाब से चेक करूँ कि आप इसके लिए eligible हैं?")
            return " ".join(parts)

        elif language == "hinglish":
            parts = []
            if scheme_name:
                intro = f"Dekho, {scheme_name} ek bahut kaam ki government scheme hai"
                if category:
                    intro += f" — especially {category} ke liye"
                parts.append(intro + ".")
            if desc:
                parts.append(desc.rstrip(".") + ".")
            if benefits:
                parts.append(f"Iske through aapko {benefits} mil sakta hai — bilkul free ya subsidized rate pe.")
            if eligibility:
                clean_elig = re.sub(r"\s+", " ", eligibility)
                parts.append(f"Eligibility ki baat karo toh — {clean_elig}.")
            parts.append("Chahte ho main aapki details dekh ke bataun ki aap qualify karte ho ya nahi?")
            return " ".join(parts)

        else:
            parts = []
            if scheme_name:
                intro = f"So, {scheme_name} is actually a really useful government program"
                if category:
                    intro += f" — it falls under {category}"
                parts.append(intro + ".")
            if desc:
                parts.append(desc.rstrip(".") + ".")
            if benefits:
                parts.append(f"The main benefit here is {benefits}.")
            if eligibility:
                clean_elig = re.sub(r"\s+", " ", eligibility)
                parts.append(f"In terms of who can apply — {clean_elig}.")
            parts.append("Would you like me to check if you're eligible based on your age and income?")
            return " ".join(parts)