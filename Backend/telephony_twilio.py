"""
Telephony Bridge for Twilio / Exotel / Plivo Integration.
Enables Indian citizens to call a phone number (PSTN / Mobile) and talk directly with the AI Assistant.

Supported Architectures:
1. WebSocket Media Streams (<Stream url="wss://.../ws/telephony/stream"/>):
   - Full duplex bi-directional audio stream (mulaw 8000Hz).
   - Real-time STT via Sarvam / Deepgram / Whisper -> Streaming LLM -> Streaming TTS.

2. TwiML Gather Voice (<Gather input="speech" language="hi-IN" action="/api/telephony/voice">):
   - Zero-infra telephone turn: Twilio does STT -> calls webhook -> Assistant generates response -> Twilio speaks via <Say> or plays TTS audio.
"""

import os
import ssl
import json
import base64
import logging
import certifi
import aiohttp
from typing import Dict, Any, Optional
from aiohttp import web

from Backend.config import TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER

logger = logging.getLogger("telephony")


async def initiate_outbound_call(to_phone: str, webhook_base_url: str) -> Dict[str, Any]:
    """
    Triggers an outbound call to a citizen's phone number via Twilio API.
    When the user picks up, Twilio fetches /api/telephony/incoming to start the voice AI dialog.
    """
    if not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN:
        raise ValueError("TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN must be configured.")

    from_phone = TWILIO_PHONE_NUMBER
    if not from_phone:
        raise ValueError("TWILIO_PHONE_NUMBER is not set in .env. Please add your Twilio phone number.")

    webhook_url = f"{webhook_base_url.rstrip('/')}/api/telephony/incoming"
    api_url = f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_ACCOUNT_SID}/Calls.json"

    data = {
        "To": to_phone,
        "From": from_phone,
        "Url": webhook_url
    }

    auth_str = base64.b64encode(f"{TWILIO_ACCOUNT_SID}:{TWILIO_AUTH_TOKEN}".encode()).decode()
    headers = {
        "Authorization": f"Basic {auth_str}",
        "Content-Type": "application/x-www-form-urlencoded"
    }

    ssl_ctx = ssl.create_default_context(cafile=certifi.where())

    async with aiohttp.ClientSession() as session:
        async with session.post(api_url, data=data, headers=headers, ssl=ssl_ctx) as resp:
            resp_data = await resp.json()
            if resp.status in (200, 201):
                logger.info(f"Outbound call initiated to {to_phone}: SID {resp_data.get('sid')}")
                return {"status": "queued", "call_sid": resp_data.get("sid"), "to": to_phone}
            else:
                logger.error(f"Twilio call failed ({resp.status}): {resp_data}")
                return {"status": "error", "error": resp_data.get("message", "Twilio API error")}


async def twilio_incoming_call_handler(request: web.Request) -> web.Response:
    """
    Webhook called when a citizen dials the Twilio phone number.
    Returns TwiML that greets the caller and starts listening in Hindi / Indian English.
    """
    twiml_response = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say language="hi-IN" voice="Polly.Aditi">
        नमस्ते! जन सेवा एआई में आपका स्वागत है। आप सरकारी योजनाओं, स्किल ट्रेनिंग या लोन के बारे में पूछ सकते हैं।
    </Say>
    <Gather input="speech" 
            language="hi-IN" 
            action="/api/telephony/voice" 
            method="POST" 
            speechTimeout="auto" 
            timeout="5">
    </Gather>
    <Say language="hi-IN" voice="Polly.Aditi">
        हमें आपकी आवाज़ नहीं सुनाई दी। कृपया दोबारा प्रयास करें।
    </Say>
</Response>"""
    return web.Response(text=twiml_response, content_type="application/xml")


async def twilio_voice_webhook_handler(request: web.Request) -> web.Response:
    """
    Processes caller speech transcript from Twilio <Gather> and returns next response.
    """
    from Backend.agent_orchestrator import orchestrator

    data = await request.post()
    speech_result = data.get("SpeechResult", "").strip()
    call_sid = data.get("CallSid", "phone_call_default")
    caller_phone = data.get("From", "unknown_phone")

    logger.info(f"Incoming phone call speech from {caller_phone} ({call_sid}): {speech_result}")

    if not speech_result:
        twiml = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say language="hi-IN" voice="Polly.Aditi">माफ़ कीजिए, हम समझ नहीं पाए। कृपया फिर से बोलें।</Say>
    <Gather input="speech" language="hi-IN" action="/api/telephony/voice" method="POST" speechTimeout="auto"/>
</Response>"""
        return web.Response(text=twiml, content_type="application/xml")

    # Process turn with orchestrator
    result = await orchestrator.handle_user_input(
        session_id=call_sid,
        user_text=speech_result
    )

    ai_answer = result.get("response", "")
    detected_lang = result.get("detected_language", "hi")

    # Map language to suitable Twilio Polly voice
    voice_name = "Polly.Aditi" if detected_lang in ("hi", "hinglish") else "Polly.Raveena"
    lang_code = "hi-IN" if detected_lang in ("hi", "hinglish") else "en-IN"

    # Clean text of markdown / symbols for clean phone TTS
    clean_speech = ai_answer.replace("**", "").replace("#", "").replace("`", "")

    twiml_response = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say language="{lang_code}" voice="{voice_name}">{clean_speech}</Say>
    <Gather input="speech" 
            language="hi-IN" 
            action="/api/telephony/voice" 
            method="POST" 
            speechTimeout="auto" 
            timeout="5">
    </Gather>
    <Say language="{lang_code}" voice="{voice_name}">धन्यवाद! जन सेवा हेल्पलाइन से जुड़ने के लिए आभार।</Say>
</Response>"""
    return web.Response(text=twiml_response, content_type="application/xml")


async def twilio_outbound_call_handler(request: web.Request) -> web.Response:
    """
    REST API endpoint to trigger a phone call:
    POST /api/telephony/call
    Body: {"to": "+919876543210", "base_url": "https://xyz.ngrok-free.app"}
    """
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON"}, status=400)

    to_phone = data.get("to")
    base_url = data.get("base_url")

    if not to_phone:
        return web.json_response({"error": "Missing 'to' phone number."}, status=400)
    if not base_url:
        return web.json_response({"error": "Missing 'base_url' (your public ngrok/domain URL)."}, status=400)

    try:
        res = await initiate_outbound_call(to_phone, base_url)
        return web.json_response(res)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)
