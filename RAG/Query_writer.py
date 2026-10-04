"""
Query Writer, Language Detector, and Multilingual Query Normalizer.
Translates Indic / Hinglish queries into clean search queries for RAG
while resolving multi-turn conversational references and preserving dialect context.
"""

import re
import os
import logging
from typing import Dict, Any, Tuple, Optional, List
from openai import OpenAI

logger = logging.getLogger(__name__)

# Common Hinglish and Devanagari Hindi terms mapped to English concepts
HINGLISH_PATTERNS = {
    r"\bumar\b|\bayu\b|\bsaal\b|उम्र|आयु|वर्ष|साल": "age",
    r"\bkamai\b|\bvetan\b|\bkharche\b|\bpaisa\b|\bpese\b|\bincome\b|\brupya\b|कमाई|वेतन|आय|रुपये|पैसे": "income",
    r"\bkisan\b|\bkheti\b|\bkrishi\b|किसान|खेती|कृषि": "farmer agriculture kisan",
    r"\bnaukri\b|\brozgar\b|\bkaam\b|\bjob\b|नौकरी|रोजगार|काम": "job employment",
    r"\bhospital\b|\bilaj\b|\bdawa\b|\bswasthya\b|\bbiemari\b|आयुष्मान|अस्पताल|इलाज|स्वास्थ्य|बीमारी": "health medical hospital ayushman",
    r"\bthela\b|\brehri\b|\bpatri\b|\bvendor\b|\bdukan\b|ठेला|रेहड़ी|दुकान|पटरी": "street vendor svanidhi",
    r"\bbeti\b|\bladhki\b|\bmahila\b|\baurat\b|बेटी|लड़की|महिला|औरत|सुकन्या": "girl woman sukanya",
    r"\byojana\b|\bscheme\b|\bsarkari\b|योजना|सरकारी|स्कीम": "government scheme welfare",
    r"\bpadhai\b|\bcourse\b|\bsikho\b|\btraining\b|\bhunar\b|कौशल|ट्रेनिंग|प्रशिक्षण|पढ़ाई|कोर्स": "skill training course pmkvy",
    r"\bkarz\b|\bloan\b|\brin\b|ऋण|कर्ज|मुद्रा|लोन": "loan credit mudra",
    r"पीएम|प्रधानमंत्री": "pm pradhan mantri",
}

KNOWN_SCHEMES = [
    "pmkvy", "kaushal", "skill", "training",
    "ayushman", "pmjay", "health", "hospital",
    "pm_kisan", "pm kisan", "kisan", "farmer", "agriculture",
    "pm_svanidhi", "svanidhi", "street vendor", "thela",
    "mudra", "business loan", "shishu", "tarun", "kishore",
    "sukanya", "ssy", "girl child", "beti",
    "naps", "apprenticeship"
]


def detect_language(text: str) -> str:
    """
    Detects language: 'hi' (Devanagari Hindi), 'hinglish' (Latin Hindi), or 'en' (English).
    """
    if not text:
        return "en"

    # Check for Devanagari Unicode block (\u0900-\u097F)
    devanagari_count = len(re.findall(r"[\u0900-\u097F]", text))
    if devanagari_count > 2 or (devanagari_count > 0 and devanagari_count / len(text) > 0.15):
        return "hi"

    # Check for Hinglish markers in Latin text
    text_lower = text.lower()
    hinglish_markers = [
        "mujhe", "mera", "meri", "hum", "aap", "kaise", "kya", "hoga", "chahiye",
        "karen", "yojana", "sarkari", "umar", "saal", "paisa", "rupaye", "milenge",
        "kaise", "karna", "hai", "batao", "bataiye", "kheti", "naukri", "ilaj", "kisan",
        "isme", "usme", "iske", "uske", "wali", "wala"
    ]
    words = re.findall(r"\b\w+\b", text_lower)
    match_count = sum(1 for w in words if w in hinglish_markers)
    if match_count >= 1:
        return "hinglish"

    return "en"


def extract_user_attributes(text: str) -> Dict[str, Any]:
    """
    Extracts citizen attributes (age, income, state, occupation) from text deterministically.
    """
    data: Dict[str, Any] = {}
    text_lower = text.lower()

    # 1. Age extraction
    age_match = re.search(r"(?:age|umar|aayu|saal|years old|उम्र|आयु|वर्ष)\s*(?:is|hai|:)?\s*(\d{1,2})", text_lower)
    if not age_match:
        age_match = re.search(r"\b(\d{1,2})\s*(?:saal|years?|yrs?|वर्ष|साल)\b", text_lower)
    if age_match:
        try:
            age_val = int(age_match.group(1))
            if 1 <= age_val <= 110:
                data["age"] = age_val
        except ValueError:
            pass

    # 2. Income extraction
    income_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:lakh|lac|lpa|लाख)", text_lower)
    if income_match:
        data["annual_income"] = float(income_match.group(1)) * 100000.0
    else:
        monthly_match = re.search(r"(\d{3,7})\s*(?:per month|\/month|mahina|mahine|प्रति माह|महीना)", text_lower)
        if monthly_match:
            data["monthly_income"] = float(monthly_match.group(1))
            data["annual_income"] = float(monthly_match.group(1)) * 12.0
        else:
            k_match = re.search(r"(\d+)\s*k\s*(?:income|kamai|salary)", text_lower)
            if k_match:
                data["monthly_income"] = float(k_match.group(1)) * 1000.0
                data["annual_income"] = float(k_match.group(1)) * 12000.0

    # 3. Occupation extraction
    if any(k in text_lower for k in ["kisan", "farmer", "kheti", "cultivator", "agriculture", "किसान", "खेती", "कृषि"]):
        data["occupation"] = "Farmer"
    elif any(k in text_lower for k in ["thela", "street vendor", "hawker", "rehri", "vendor", "stall", "ठेला", "फेरीवाला", "रेहड़ी"]):
        data["occupation"] = "Street Vendor"
    elif any(k in text_lower for k in ["unemployed", "berozgar", "jobless", "fresher", "no job", "बेरोजगार", "बेरोज़गार"]):
        data["occupation"] = "Unemployed"
    elif any(k in text_lower for k in ["student", "padhai", "college", "school", "छात्र", "विद्यार्थी", "पढ़ाई"]):
        data["occupation"] = "Student"
    elif any(k in text_lower for k in ["dukan", "shopkeeper", "vyapari", "small business", "dukaandar", "दुकानदार", "व्यापारी"]):
        data["occupation"] = "Shopkeeper"

    # 4. State extraction
    indian_states = [
        "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chhattisgarh",
        "Goa", "Gujarat", "Haryana", "Himachal Pradesh", "Jharkhand", "Karnataka",
        "Kerala", "Madhya Pradesh", "Maharashtra", "Manipur", "Meghalaya", "Mizoram",
        "Nagaland", "Odisha", "Punjab", "Rajasthan", "Sikkim", "Tamil Nadu",
        "Telangana", "Tripura", "Uttar Pradesh", "Uttarakhand", "West Bengal",
        "Delhi", "Jammu and Kashmir", "Ladakh"
    ]
    for state in indian_states:
        if state.lower() in text_lower:
            data["state"] = state
            break

    # 5. Gender
    if any(k in text_lower for k in ["female", "aurat", "mahila", "woman", "ladki", "girl", "महिला", "औरत", "लड़की", "बेटी"]):
        data["gender"] = "Female"
    elif any(k in text_lower for k in ["male", "purush", "man", "ladka", "boy", "पुरुष", "लड़का", "बेटा"]):
        data["gender"] = "Male"

    return data


class Query_writer:
    """
    Translates and normalizes multilingual user queries into English structured queries for RAG
    with multi-turn conversational context resolution.
    """

    def __init__(self, api_key: str = "", url: Optional[str] = None):
        self.url = url or os.getenv("OPENAI_BASE_URL", "https://api.groq.com/openai/v1")
        self.api_key = api_key or os.getenv("OPENAI_API_KEY", "")
        self.model = os.getenv("DEFAULT_LLM_MODEL", "qwen/qwen3.8-27b")
        try:
            if not self.api_key:
                logger.warning("No LLM API key set — translation will use offline heuristics.")
                self.client = None
            else:
                self.client = OpenAI(
                    api_key=self.api_key,
                    base_url=self.url,
                    max_retries=1,
                    timeout=8.0
                )
        except Exception as e:
            logger.warning(f"OpenAI client initialization warning: {e}")
            self.client = None

    def detect_lang(self, query: str) -> str:
        """Returns detected language code ('en', 'hi', or 'hinglish')."""
        return detect_language(query)

    def write_qwery(self, query: str, conversation_history: Optional[List[Dict[str, str]]] = None) -> Any:
        """
        Calls LLM to contextualize and translate query into a self-contained English search query.
        Falls back to local heuristic normalization if LLM is offline.
        """
        if self.client:
            try:
                system_prompt = (
                    "You are a search query optimizer for an Indian government schemes voice assistant. "
                    "Given the recent conversation history and the user's latest query, rewrite the query into a "
                    "concise, self-contained English keyword search query. "
                    "IMPORTANT: Resolve all pronoun references (e.g., 'it', 'this', 'iska', 'usme', 'apply kaise karein' -> "
                    "name of the scheme discussed). Return ONLY the rewritten search query with no quotes or explanation."
                )

                messages = [{"role": "system", "content": system_prompt}]

                # Include past 4 turns for context resolution
                if conversation_history:
                    for turn in conversation_history[-4:]:
                        role = turn.get("role", "")
                        content = turn.get("content", "")
                        if role in ("user", "assistant") and content:
                            messages.append({"role": role, "content": content})

                messages.append({
                    "role": "user",
                    "content": f"User's latest message: {query}"
                })

                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=0.2,
                    max_tokens=100,
                    timeout=4.0,
                )
                return response
            except Exception as e:
                logger.debug(f"LLM translation call failed, using heuristic normalization: {e}")

        # Fallback pseudo-response object matching OpenAI response structure
        normalized = self.normalize_query_offline(query, conversation_history)
        return type("MockResponse", (), {
            "choices": [
                type("MockChoice", (), {
                    "message": type("MockMessage", (), {"content": normalized})()
                })()
            ]
        })()

    def normalize_query_offline(self, query: str, conversation_history: Optional[List[Dict[str, str]]] = None) -> str:
        """Heuristic normalization with multi-turn context awareness."""
        translated = query.lower()
        for pattern, replacement in HINGLISH_PATTERNS.items():
            translated = re.sub(pattern, replacement, translated)

        # Contextual carry-forward if user asks follow-up (e.g. "how to apply", "eligibility kya hai")
        followup_markers = ["apply", "documents", "eligibility", "process", "portal", "website", "benefits", "karein", "kaise", "iska", "usme", "isme", "it", "this", "details"]
        if any(m in translated for m in followup_markers) and conversation_history:
            # Find last mentioned scheme in history
            for turn in reversed(conversation_history[-4:]):
                content = turn.get("content", "").lower()
                for scheme in KNOWN_SCHEMES:
                    if scheme in content:
                        translated = f"{scheme} {translated}"
                        break
                else:
                    continue
                break

        return translated.strip()
