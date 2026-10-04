"""
High-Performance Asynchronous Web & WebSocket Server.
Implements low-latency WebSocket audio streaming, REST APIs for scheme search & eligibility,
and serves the Citizen Portal UI.
"""

import sys
import json
import base64
import logging
from pathlib import Path
from aiohttp import web

@web.middleware
async def cors_middleware(request: web.Request, handler) -> web.Response:
    if request.method == "OPTIONS":
        resp = web.Response()
    else:
        resp = await handler(request)
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    return resp

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from Backend.config import HOST, PORT, FRONTEND_DIR
from Backend.agent_orchestrator import orchestrator
from Backend.session_manager import session_registry
from Database.session import SessionLocal, init_db
from Database.models import SchemeModel
from Database.rules_engine import EligibilityRulesEngine
from RAG.Indegstion import run_ingestion

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("server")


async def health_handler(request: web.Request) -> web.Response:
    """Health check endpoint."""
    return web.json_response({
        "status": "healthy",
        "service": "AI Voice Assistant - Indian Citizen Welfare",
        "version": "1.0.0"
    })


async def index_handler(request: web.Request) -> web.FileResponse:
    """Serves the primary citizen portal HTML."""
    index_path = FRONTEND_DIR / "index.html"
    if not index_path.exists():
        return web.Response(text="Frontend index.html not found.", status=404)
    return web.FileResponse(index_path)


async def chat_handler(request: web.Request) -> web.Response:
    """REST endpoint for single-turn or multi-turn conversational interaction."""
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON"}, status=400)

    user_text = data.get("text", "")
    session_id = data.get("session_id", "default_session")

    result = await orchestrator.handle_user_input(
        session_id=session_id,
        user_text=user_text
    )
    return web.json_response(result)


async def schemes_handler(request: web.Request) -> web.Response:
    """Lists all available government schemes with optional category filtering."""
    category = request.query.get("category")
    with SessionLocal() as db:
        query = db.query(SchemeModel)
        if category:
            query = query.filter(SchemeModel.category.ilike(f"%{category}%"))
        schemes = query.all()
        return web.json_response([
            {
                "scheme_id": s.scheme_id,
                "name": s.name,
                "category": s.category,
                "description": s.description,
                "min_age": s.min_age,
                "max_age": s.max_age,
                "max_annual_income": s.max_annual_income,
                "eligible_occupations": s.eligible_occupations,
                "eligible_states": s.eligible_states,
                "benefits": s.benefits,
                "portal_url": s.portal_url
            }
            for s in schemes
        ])


async def check_eligibility_handler(request: web.Request) -> web.Response:
    """Direct deterministic eligibility calculation against all schemes."""
    try:
        user_data = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON"}, status=400)

    session_id = user_data.get("session_id", "adhoc_session")
    with SessionLocal() as db:
        rules_engine = EligibilityRulesEngine(db)
        results = rules_engine.check_all_schemes(user_data)
        rules_engine.save_evaluation(session_id, results)
        return web.json_response({
            "session_id": session_id,
            "results": [
                {
                    "scheme_id": r.scheme_id,
                    "scheme_name": r.scheme_name,
                    "category": r.category,
                    "is_eligible": r.is_eligible,
                    "match_score": r.match_score,
                    "matched_criteria": r.matched_criteria,
                    "unmatched_criteria": r.unmatched_criteria,
                    "summary": r.summary,
                    "portal_url": r.portal_url,
                    "benefits": r.benefits
                }
                for r in results
            ]
        })


async def get_session_handler(request: web.Request) -> web.Response:
    """Retrieves session profile attributes, persistent dialogue history, and eligible schemes."""
    session_id = request.match_info.get("session_id", "default_session")
    session = session_registry.get_or_create(session_id)
    eligible = []
    if session.attributes:
        with SessionLocal() as db:
            rules_engine = EligibilityRulesEngine(db)
            all_matches = rules_engine.check_all_schemes(session.attributes)
            eligible = [
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
                for s in all_matches if s.is_eligible
            ][:4]

    return web.json_response({
        "session_id": session_id,
        "attributes": session.attributes,
        "history": session.history,
        "eligible_schemes": eligible
    })


async def reset_session_handler(request: web.Request) -> web.Response:
    """Resets user session state and demographic memory."""
    session_id = request.match_info.get("session_id", "default_session")
    session_registry.reset_session(session_id)
    return web.json_response({"status": "reset", "session_id": session_id})


async def ingest_handler(request: web.Request) -> web.Response:
    """Triggers re-indexing of documents."""
    count = run_ingestion()
    return web.json_response({"status": "success", "indexed_chunks": count})


async def websocket_audio_handler(request: web.Request) -> web.WebSocketResponse:
    """
    True streaming WebSocket handler.

    Flow per turn:
      1. STT / text received
      2. Language detect + entity extract + eligibility (fast, local) → sent to frontend immediately
      3. RAG retrieval + Groq STREAMING → each sentence is yielded as it arrives
      4. Each sentence → TTS synthesis → audio_chunk sent to frontend
         (first audio plays before the last sentence is even generated)
    """
    import asyncio
    ws = web.WebSocketResponse(heartbeat=30)
    await ws.prepare(request)
    logger.info("WebSocket client connected.")

    active_session_id = "ws_session"

    async def process_turn(target_session_id: str, user_text: str, audio_bytes: bytes = b""):
        """Runs one full conversation turn with streaming LLM + TTS."""
        session = session_registry.get_or_create(target_session_id)
        session.reset_interruption()

        # ── STT ──────────────────────────────────────────────────────────────
        if audio_bytes:
            await ws.send_json({"type": "status", "status": "transcribing"})
            stt_result = await orchestrator.stt.transcribe_audio_bytes(audio_bytes)
            if stt_result.get("transcript"):
                user_text = stt_result["transcript"]
                await ws.send_json({"type": "transcript", "text": user_text})

        user_text = user_text.strip()
        if not user_text:
            await ws.send_json({"type": "status", "status": "idle"})
            return

        await ws.send_json({"type": "status", "status": "thinking"})

        # ── Language + Entity extraction (instant) ───────────────────────────
        from RAG.Query_writer import detect_language, extract_user_attributes
        detected_lang = detect_language(user_text)
        extracted = extract_user_attributes(user_text)
        if extracted:
            session.update_attributes(extracted)
        session.add_message("user", user_text, detected_lang)

        # ── Eligibility (deterministic, fast) ────────────────────────────────
        from Database.session import SessionLocal
        from Database.rules_engine import EligibilityRulesEngine
        eligible_schemes = []
        with SessionLocal() as db:
            engine = EligibilityRulesEngine(db)
            matches = engine.check_all_schemes(session.attributes)
            eligible_schemes = [m for m in matches if m.is_eligible][:4]
            if session.attributes:
                engine.save_evaluation(target_session_id, eligible_schemes)

        # ── Build history for LLM ─────────────────────────────────────────────
        history_for_llm = [
            {"role": t["role"], "content": t["content"]}
            for t in session.history[-8:]
            if t.get("role") in ("user", "assistant") and t.get("content")
        ]

        # ── Send profile + scheme update to frontend immediately ──────────────
        await ws.send_json({
            "type": "profile_update",
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
            "detected_language": detected_lang
        })

        # ── Stream LLM → TTS concurrently ────────────────────────────────────
        full_response_parts = []
        sources = []
        sentence_idx = 0

        async for event in orchestrator.rag.stream_grounded_answer(
            query=user_text,
            user_demographics=session.attributes,
            language=detected_lang,
            conversation_history=history_for_llm
        ):
            if session.interruption_event.is_set():
                await ws.send_json({"type": "interrupted"})
                return

            if event["type"] == "meta":
                # Sources + language confirmed — update frontend
                sources = event.get("sources", [])
                await ws.send_json({
                    "type": "meta",
                    "sources": sources,
                    "detected_language": event.get("detected_language", detected_lang)
                })
                continue

            if event["type"] == "sentence":
                sentence_text = event.get("text", "").strip()
                is_final = event.get("is_final", False)

                if sentence_text:
                    full_response_parts.append(sentence_text)

                    # Stream this sentence as text token immediately
                    await ws.send_json({
                        "type": "token",
                        "text": sentence_text,
                        "sentence_index": sentence_idx
                    })

                    # Synthesize audio for this sentence immediately (don't wait for rest)
                    audio_result = await orchestrator.tts.synthesize_chunk(sentence_text, detected_lang)
                    if audio_result and not session.interruption_event.is_set():
                        await ws.send_json({
                            "type": "audio_chunk",
                            "sentence_index": sentence_idx,
                            **audio_result
                        })
                    sentence_idx += 1

                if is_final:
                    break

        full_response = " ".join(full_response_parts)

        # Proactive eligibility mention — appended naturally
        eligibility_kws = ["eligible", "patra", "apply", "qualify", "mera", "milega", "milegi", "benefit"]
        if eligible_schemes and any(k in user_text.lower() for k in eligibility_kws):
            top = eligible_schemes[:2]
            if detected_lang == "hi":
                extra = " और ".join([s.scheme_name for s in top])
                suffix = f" वैसे, {extra} के लिए आप eligible हो सकते हैं — चाहते हो और जानकारी दूँ?"
            elif detected_lang == "hinglish":
                extra = " aur ".join([s.scheme_name for s in top])
                suffix = f" Aur sun, {extra} ke liye tum qualify kar sakte ho — kya main aur detail bataun?"
            else:
                extra = " and ".join([s.scheme_name for s in top])
                suffix = f" By the way, you might qualify for {extra} — want me to walk you through those?"
            full_response += suffix
            # Speak the eligibility suffix too
            audio_result = await orchestrator.tts.synthesize_chunk(suffix.strip(), detected_lang)
            if audio_result and not session.interruption_event.is_set():
                await ws.send_json({"type": "audio_chunk", "sentence_index": sentence_idx, **audio_result})

        # ── Persist assistant message ─────────────────────────────────────────
        session.add_message("assistant", full_response, detected_lang, sources=sources)

        await ws.send_json({
            "type": "response_complete",
            "full_response": full_response,
            "sources": sources
        })
        await ws.send_json({"type": "audio_complete"})

    try:
        async for msg in ws:
            if msg.type == web.WSMsgType.TEXT:
                try:
                    payload = json.loads(msg.data)
                except Exception:
                    continue

                action = payload.get("action")
                active_session_id = payload.get("session_id", active_session_id)
                session = session_registry.get_or_create(active_session_id)

                if action == "interrupt":
                    session.signal_interruption()
                    await ws.send_json({"type": "interrupted"})

                elif action == "text_message":
                    await process_turn(
                        target_session_id=active_session_id,
                        user_text=payload.get("text", "")
                    )

                elif action == "audio_data":
                    b64 = payload.get("audio_base64", "")
                    import base64 as _b64
                    audio_bytes = _b64.b64decode(b64) if b64 else b""
                    await process_turn(
                        target_session_id=active_session_id,
                        user_text="",
                        audio_bytes=audio_bytes
                    )

            elif msg.type == web.WSMsgType.ERROR:
                logger.error(f"WebSocket error: {ws.exception()}")

    finally:
        logger.info(f"WebSocket disconnected: {active_session_id}")

    return ws



def create_app() -> web.Application:
    """Builds and configures the aiohttp application."""
    init_db()
    app = web.Application(middlewares=[cors_middleware])

    # Route definitions
    app.router.add_get("/", index_handler)
    app.router.add_get("/health", health_handler)
    app.router.add_get("/ws/audio", websocket_audio_handler)
    app.router.add_post("/api/chat", chat_handler)
    app.router.add_get("/api/schemes", schemes_handler)
    app.router.add_post("/api/check-eligibility", check_eligibility_handler)
    app.router.add_get("/api/session/{session_id}", get_session_handler)
    app.router.add_post("/api/session/{session_id}/reset", reset_session_handler)
    app.router.add_post("/api/ingest", ingest_handler)

    # Telephony Webhooks (Twilio / Exotel / Plivo)
    from Backend.telephony_twilio import (
        twilio_incoming_call_handler,
        twilio_voice_webhook_handler,
        twilio_outbound_call_handler
    )
    app.router.add_post("/api/telephony/incoming", twilio_incoming_call_handler)
    app.router.add_get("/api/telephony/incoming", twilio_incoming_call_handler)
    app.router.add_post("/api/telephony/voice", twilio_voice_webhook_handler)
    app.router.add_post("/api/telephony/call", twilio_outbound_call_handler)

    if FRONTEND_DIR.exists():
        app.router.add_static("/static", path=FRONTEND_DIR, name="static")

    return app


if __name__ == "__main__":
    app = create_app()
    logger.info(f"Starting Citizen Welfare Assistant Server on http://{HOST}:{PORT}")
    web.run_app(app, host=HOST, port=PORT)
