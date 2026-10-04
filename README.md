# 🇮🇳 Jan Seva AI - Multilingual Voice Assistant for Indian Citizen Welfare

[![Python 3.11](https://img.shields.io/badge/Python-3.11-blue.svg)](https://www.python.org/)
[![Fast WebSocket Streaming](https://img.shields.io/badge/WebSocket-Full--Duplex-emerald.svg)]()
[![Groq Powered](https://img.shields.io/badge/Groq-Qwen%203.8--27B-orange.svg)](https://groq.com/)
[![Twilio Telephony](https://img.shields.io/badge/Telephony-Twilio%20PSTN-red.svg)](https://www.twilio.com/)
[![Tests Passing](https://img.shields.io/badge/Tests-19%2F19%20Passing-brightgreen.svg)]()

**Jan Seva AI** is a real-time, voice-first AI assistant built for Indian citizens. It acts as an empathetic counselor and guide to help citizens discover, understand, and verify eligibility for government welfare schemes, skill training programs (PMKVY), health insurance (Ayushman Bharat), micro-loans (PM SVANidhi / MUDRA), and job opportunities.

It supports seamless code-switching across **English, Hindi (Devanagari), and Hinglish**, runs a **deterministic rules engine** for 100% accurate financial & age eligibility calculations, streams audio concurrently, and can be accessed via **Web Browser** or **Real Phone Calls (PSTN / Twilio)**.

---

## 🌟 Key Capabilities & Features

### 1. ⚡ Real-Time Token & Audio Streaming (Sub-300ms First-Audio Latency)
- **Token-to-Sentence Streaming:** Groq (`qwen/qwen3.8-27b`) streams tokens over full-duplex WebSockets (`/ws/audio`).
- **Concurrent Synthesis:** The server cuts sentences at natural breath boundaries (`.`, `?`, `!`, `।`) and fires TTS on sentence #1 immediately. Audio starts playing on the user's device while sentences #2 and #3 are still generating.
- **Barge-In Interruption:** Speaking or tapping the mic instantly halts server TTS and cancels pending audio queues.

### 2. 🧠 Multi-Turn Memory & Pronoun Resolution
- Remembers context across turns: When a citizen asks follow-up questions (e.g. *"Isme apply kaise karein?"* or *"What documents are needed?"*), the contextual query rewriter resolves *"isme"* or *"it"* back to the scheme discussed in previous turns before executing RAG retrieval.
- Retains demographic profiles (`age`, `income`, `occupation`, `state`) across page reloads in SQLite.

### 3. 🗣️ Conversational Persona ("Sahayak")
- Replaced robotic document dumps and markdown tables with warm, natural, human-like dialogue.
- Speaks naturally as a helpful *bhaiya/didi* or *dost* in Hindi, Hinglish, or Indian English.

### 4. ⚖️ Hybrid Deterministic Rules Engine (Zero-Hallucination)
- **No arithmetic or boundary evaluation is delegated to LLMs.**
- A pure Python rules engine (`Database/rules_engine.py`) deterministically checks age bounds, income ceilings (converting monthly to annual income), state exclusions, and occupation matching directly against SQLite database records.

### 5. 📞 Real Phone Call Integration (Telephony / PSTN)
- Integrated Twilio Voice webhooks for incoming and outgoing phone calls:
  - `POST /api/telephony/incoming`: Greets callers in Hindi/English upon answering.
  - `POST /api/telephony/voice`: Captures speech via `<Gather>` and streams the AI answer back over the cellular phone call.
  - `POST /api/telephony/call`: Outbound dialer API.
  - CLI dialer utility: `python dial_phone_call.py <PHONE_NUMBER> <BASE_URL>`.

### 6. 🎙️ High-Accuracy STT & Voice Engine
- Web Speech API configured with `interimResults = true` and `hi-IN` locale mapping for live transcription feedback (*"Listening..."*).
- Pluggable support for **Sarvam AI (Saarika STT / Bulbul TTS)** with graceful zero-cost browser voice fallbacks (`Meera`, `Ravi`, `Priya`).

---

## 📂 Project Structure

```
├── AGENTS.md                  # Project rules & core architectural directives
├── ARCHITECTURE.md            # Comprehensive architecture & complexity reference
├── Backend/                   # Server, Orchestrator, Session & Telephony
│   ├── agent_orchestrator.py  # End-to-end loop coordinator
│   ├── config.py              # Environment settings & model routing
│   ├── server.py              # Async aiohttp server & streaming WebSocket handler
│   ├── session_manager.py     # Persistent multi-turn session state & SQLite logger
│   └── telephony_twilio.py    # Twilio PSTN voice webhook handlers & dialer
├── Database/                  # Relational DB & Deterministic Rules
│   ├── assistant.db           # SQLite database (auto-seeded)
│   ├── models.py              # SQLAlchemy models (User, Scheme, Check, Log)
│   ├── rules_engine.py        # 100% deterministic eligibility engine
│   └── session.py             # DB engine & seeder
├── Documents/                 # Verified Government Schemes Knowledge Base
│   ├── schemes_knowledge_base.json
│   ├── pmkvy.md               # PMKVY 4.0 Skill Training
│   ├── ayushman_bharat.md     # PM-JAY Healthcare ₹5 Lakh
│   ├── pm_kisan.md            # PM-KISAN ₹6,000 Direct Benefit Transfer
│   ├── pm_svanidhi.md         # PM SVANidhi Street Vendor Loans
│   ├── mudra_yojana.md        # PMMY Micro-Enterprise Business Loans
│   ├── sukanya_samriddhi.md   # SSY Girl Child Savings Scheme
│   └── naps.md                # National Apprenticeship Promotion Scheme
├── Frontend/                  # Modern Web Citizen Portal
│   └── index.html             # Responsive Tailwind CSS voice UI with streaming text & audio
├── Models/                    # Local GGUF models for offline fallback
│   ├── Qwen2.5-0.5B-Instruct-Q4_K_M.gguf
│   ├── sarvam-1-v0.5-Q8_0.gguf
│   └── phi4mini-shoprag-4bb-q4km-imx.gguf
├── RAG/                       # Grounded Retrieval & Contextual Query Processing
│   ├── Indegstion.py          # Document loader, chunker & indexer (53 chunks)
│   ├── Query_writer.py        # Multilingual detector & multi-turn query rewriter
│   └── Retrival.py            # Grounded retriever & real-time streaming synthesizer
├── STT/                       # Speech-to-Text & Text-to-Speech Modules
│   ├── stt_engine.py          # Sarvam Saarika + Web Speech bridge
│   └── TTS/
│       └── tts_engine.py      # Sarvam Bulbul + chunked sentence streamer
├── Tests/                     # Automated Test Suites (19 Tests Passing)
│   ├── test_orchestrator.py   # End-to-end multi-turn integration tests
│   ├── test_persistence.py    # Database persistence & conversational summary tests
│   ├── test_rag_pipeline.py   # Grounding, language detection & entity extraction
│   ├── test_rules_engine.py   # Boundary & math eligibility tests
│   └── test_server_api.py     # In-memory REST & Telephony API tests
├── dial_phone_call.py         # Outbound phone call test CLI
├── run.py                     # Main application entry point
├── requirements.txt           # Python dependencies
└── .env                       # Environment credentials (Groq, Twilio, Sarvam)
```

---

## 🚀 Quickstart Guide

### 1. Setup Virtual Environment
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure Environment (`.env`)
Create a `.env` file in the project root:
```env
# Groq Cloud LLM (Fast reasoning)
OPENAI_BASE_URL=https://api.groq.com/openai/v1
OPENAI_API_KEY=your_groq_api_key
DEFAULT_LLM_MODEL=qwen/qwen3.8-27b

# Telephony (Twilio - Optional)
TWILIO_ACCOUNT_SID=your_account_sid
TWILIO_AUTH_TOKEN=your_auth_token
TWILIO_PHONE_NUMBER=+1XXXXXXXXXX

# Sarvam AI (Optional)
SARVAM_API_KEY=

# Server
HOST=0.0.0.0
PORT=8000
```

### 3. Run Automated Tests
```bash
./.venv/bin/python3 -m unittest discover -s Tests -p "test_*.py" -v
```
*(All 19 tests will run and pass).*

### 4. Start the Voice Assistant Server
```bash
./.venv/bin/python3 run.py
```
Open your browser at:
👉 **[http://localhost:8000](http://localhost:8000)**

---

## 📱 Accessing from Mobile & Phone Calls

### Method A: Mobile Web Audio (Zero Cost)
1. In a second terminal, expose port 8000 with `ngrok` or `pinggy`:
   ```bash
   ngrok http 8000
   # OR (zero install):
   ssh -R 80:localhost:8000 a.pinggy.io
   ```
2. Open the generated `https://...` link on your phone's browser (Chrome / Safari) and tap the 🎙️ **Microphone button**.

### Method B: Inbound Cellular Phone Call (Twilio PSTN)
1. Go to your [Twilio Console](https://console.twilio.com) → **Phone Numbers** → **Manage Active Numbers**.
2. Set the **Voice Webhook (HTTP POST)** to:
   ```
   https://YOUR-PUBLIC-URL/api/telephony/incoming
   ```
3. Dial the number from your mobile phone. The assistant answers and converses with you over the phone call.

### Method C: Outbound Phone Call Trigger
Trigger an automated AI phone call to any citizen's phone number:
```bash
./.venv/bin/python3 dial_phone_call.py +919876543210 https://YOUR-PUBLIC-URL.ngrok-free.app
```

---

## 🎙️ Supported Multilingual Dialogue Examples

- **Hinglish Discovery:**  
  *User:* "Mera umar 22 saal hai, mujhe job training karni hai koi scheme hai?"  
  *AI:* "Haan bhai, iske liye Pradhan Mantri Kaushal Vikas Yojana (PMKVY 4.0) sabse best option hai..."
- **Multi-turn Context Resolution:**  
  *User:* "Isme apply kaise karein?" *(No scheme name mentioned)*  
  *AI:* "PMKVY 4.0 ke liye aapko Skill India Digital portal `skillindiadigital.gov.in` par jaakar online register karna hoga..."
- **Hindi Agriculture Support:**  
  *User:* "मेरी उम्र 40 साल है, मैं किसान हूँ, मुझे सरकारी मदद चाहिए।"  
  *AI:* "नमस्ते! आपके लिए पीएम-किसान (PM-KISAN) सम्मान निधि योजना सबसे उपयुक्त है..."
- **Strict Grounding Rejection:**  
  *User:* "Can you give me a recipe for pizza?"  
  *AI:* "I'm sorry, I don't have verified government information on that topic. Is there a specific welfare scheme or job training program I can help you with?"

---

## 📄 License & Compliance
Built in accordance with open public welfare guidelines for Indian Citizen Services. Strictly adheres to data privacy standards with on-device / local database persistence.
