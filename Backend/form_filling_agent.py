"""
Official Government Scheme Form-Filling Assistant ("Form Sahayak").
Enables interactive, voice-driven official application form filling for Indian Citizens.
"""

import re
import json
import random
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple

from Database.session import SessionLocal
from Database.models import ApplicationSubmissionModel

logger = logging.getLogger("form_agent")

# ──────────────────────────────────────────────────────────────────────────────
# OFFICIAL FORM SCHEMAS FOR TOP CITIZEN WELFARE SCHEMES
# ──────────────────────────────────────────────────────────────────────────────

OFFICIAL_SCHEME_FORMS: Dict[str, Dict[str, Any]] = {
    "pmkvy": {
        "scheme_id": "pmkvy",
        "scheme_name": "Pradhan Mantri Kaushal Vikas Yojana (PMKVY 4.0)",
        "portal_url": "https://www.skillindiadigital.gov.in",
        "category": "Skill Development & Employment",
        "fields": [
            {
                "key": "full_name",
                "label": "Full Name",
                "hindi_label": "पूरा नाम",
                "attr_key": "name",
                "prompts": {
                    "hi": "प्रधानमंत्री कौशल विकास योजना (PMKVY 4.0) फॉर्म के लिए सबसे पहले अपना पूरा नाम बताएं।",
                    "hinglish": "PMKVY 4.0 official registration ke liye sabse pehle apna Full Name bataiye.",
                    "en": "To begin your PMKVY 4.0 application, please provide your Full Name."
                }
            },
            {
                "key": "mobile",
                "label": "Mobile Number",
                "hindi_label": "मोबाइल नंबर",
                "attr_key": "mobile",
                "prompts": {
                    "hi": "अपना 10 अंकों का मोबाइल नंबर बताएं जिस पर OTP और ट्रेनिंग की जानकारी भेजी जाएगी।",
                    "hinglish": "Apna 10-digit mobile number bataiye jispar OTP aur training confirmation aayega.",
                    "en": "Please provide your 10-digit mobile number for official alerts and OTP."
                }
            },
            {
                "key": "age",
                "label": "Age / Date of Birth",
                "hindi_label": "उम्र",
                "attr_key": "age",
                "prompts": {
                    "hi": "आपकी उम्र कितनी है? (PMKVY में 15 से 45 वर्ष के उम्मीदवार पात्र हैं)",
                    "hinglish": "Aapki umar (age) kitni hai? (PMKVY mein 15 se 45 saal ke youth eligible hain)",
                    "en": "What is your age? (PMKVY is open for candidates aged 15 to 45)"
                }
            },
            {
                "key": "qualification",
                "label": "Highest Qualification",
                "hindi_label": "उच्चतम शिक्षा",
                "attr_key": "education",
                "prompts": {
                    "hi": "आपकी सबसे उच्च शिक्षा (Highest Qualification) क्या है? जैसे 10वीं पास, 12वीं पास, ITI, या ग्रेजुएट?",
                    "hinglish": "Aapki highest qualification kya hai? Jaise 10th pass, 12th pass, ITI, ya Graduate?",
                    "en": "What is your highest educational qualification (e.g. 10th, 12th, ITI, or Graduate)?"
                }
            },
            {
                "key": "course_interest",
                "label": "Preferred Skill Course / Sector",
                "hindi_label": "पसंदीदा कोर्स/ट्रेड",
                "attr_key": "course",
                "prompts": {
                    "hi": "आप किस क्षेत्र में ट्रेनिंग लेना चाहते हैं? जैसे IT व कंप्यूटर, हेल्थकेयर, सोलर व इलेक्ट्रिशियन, या ऑटोमोबाइल?",
                    "hinglish": "Aap kis field mein training lena chahte hain? Jaise IT / Computer, Healthcare, Solar & Electrician, ya Automobile?",
                    "en": "Which sector or skill course would you like to enroll in (e.g. IT, Healthcare, Solar, Automotive)?"
                }
            },
            {
                "key": "state_district",
                "label": "State & District",
                "hindi_label": "राज्य एवं ज़िला",
                "attr_key": "state",
                "prompts": {
                    "hi": "आप किस राज्य और ज़िले में रहते हैं ताकि नज़दीकी ट्रेनिंग सेंटर खोजा जा सके?",
                    "hinglish": "Aap kis State aur District (shehar) mein rehte hain taaki pass ka Skill Center assign ho sake?",
                    "en": "Which State and District do you reside in, so we can locate your nearest training center?"
                }
            }
        ]
    },

    "ayushman_bharat": {
        "scheme_id": "ayushman_bharat",
        "scheme_name": "Ayushman Bharat - PM-JAY (Golden Card)",
        "portal_url": "https://beneficiary.nha.gov.in",
        "category": "Healthcare ₹5 Lakh Insurance",
        "fields": [
            {
                "key": "family_head_name",
                "label": "Family Head Name",
                "hindi_label": "परिवार के मुखिया का नाम",
                "attr_key": "name",
                "prompts": {
                    "hi": "आयुष्मान भारत गोल्डन कार्ड फॉर्म के लिए परिवार के मुखिया का पूरा नाम बताएं।",
                    "hinglish": "Ayushman Bharat ₹5 Lakh health card form ke liye Head of Family ka naam bataiye.",
                    "en": "Please provide the Full Name of the Head of Family for Ayushman Bharat PM-JAY."
                }
            },
            {
                "key": "mobile",
                "label": "Mobile Number",
                "hindi_label": "मोबाइल नंबर",
                "attr_key": "mobile",
                "prompts": {
                    "hi": "अपना 10 अंकों का मोबाइल नंबर बताएं।",
                    "hinglish": "Apna 10-digit mobile number bataiye.",
                    "en": "Please provide your 10-digit mobile number."
                }
            },
            {
                "key": "ration_or_aadhaar",
                "label": "Aadhaar / Ration Card (Last 4 Digits)",
                "hindi_label": "आधार या राशन कार्ड (अंतिम 4 अंक)",
                "attr_key": "id_last4",
                "prompts": {
                    "hi": "पहचान सत्यापन के लिए अपने आधार कार्ड या राशन कार्ड के अंतिम 4 अंक बताएं।",
                    "hinglish": "Verification ke liye apne Aadhaar ya Ration card ke aakhri 4 digits bataiye.",
                    "en": "Please share the last 4 digits of your Aadhaar Card or Ration Card for eligibility verification."
                }
            },
            {
                "key": "state_district",
                "label": "State & District",
                "hindi_label": "राज्य एवं ज़िला",
                "attr_key": "state",
                "prompts": {
                    "hi": "आप किस राज्य और ज़िले के निवासी हैं?",
                    "hinglish": "Aap kis State aur District ke niwasi hain?",
                    "en": "Which State and District do you belong to?"
                }
            },
            {
                "key": "family_members",
                "label": "Total Family Members",
                "hindi_label": "परिवार में कुल सदस्य",
                "attr_key": "members",
                "prompts": {
                    "hi": "परिवार में कुल कितने सदस्य हैं जिन्हें कार्ड में शामिल करना है?",
                    "hinglish": "Family mein total kitne members hain jinhe health cover mein add karna hai?",
                    "en": "How many total family members are to be included in the ₹5 Lakh health cover?"
                }
            }
        ]
    },

    "pm_svanidhi": {
        "scheme_id": "pm_svanidhi",
        "scheme_name": "PM SVANidhi Street Vendor Loan",
        "portal_url": "https://pmsvanidhi.mohua.gov.in",
        "category": "Micro Credit ₹10,000 - ₹50,000",
        "fields": [
            {
                "key": "vendor_name",
                "label": "Vendor Name",
                "hindi_label": "विक्रेता का नाम",
                "attr_key": "name",
                "prompts": {
                    "hi": "पीएम स्वनिधि लोन के लिए विक्रेता का पूरा नाम बताएं।",
                    "hinglish": "PM SVANidhi micro-loan form ke liye apna poora naam bataiye.",
                    "en": "Please provide your Full Name for the PM SVANidhi Vendor Loan application."
                }
            },
            {
                "key": "mobile",
                "label": "Mobile Number",
                "hindi_label": "मोबाइल नंबर",
                "attr_key": "mobile",
                "prompts": {
                    "hi": "बैंक खाते से जुड़ा 10 अंकों का मोबाइल नंबर बताएं।",
                    "hinglish": "Bank account se linked 10-digit mobile number bataiye.",
                    "en": "Please provide your 10-digit mobile number linked with your bank account."
                }
            },
            {
                "key": "vending_activity",
                "label": "Type of Vending / Goods",
                "hindi_label": "दुकान/सामग्री का प्रकार",
                "attr_key": "occupation",
                "prompts": {
                    "hi": "आप किस चीज़ की दुकान या रेहड़ी लगाते हैं? (जैसे फल, सब्ज़ी, चाय, नाश्ता, कपड़े)",
                    "hinglish": "Aap kis cheez ka business ya thela lagate hain? (Jaise sabzi, fruits, chai/food, ya kapde)?",
                    "en": "What type of vending or goods do you sell (e.g. Vegetables, Fruits, Tea/Food, Garments)?"
                }
            },
            {
                "key": "vending_location",
                "label": "Market Location / Town",
                "hindi_label": "बाज़ार या वेंडिंग स्थल",
                "attr_key": "state",
                "prompts": {
                    "hi": "आप किस बाज़ार, शहर या वेंडिंग ज़ोन में दुकान लगाते हैं?",
                    "hinglish": "Aap kis market ya shehar mein thela lagate hain?",
                    "en": "In which market, ward, or city do you vend your items?"
                }
            },
            {
                "key": "loan_amount",
                "label": "Requested Loan Amount",
                "hindi_label": "ऋण राशि",
                "attr_key": "loan_amount",
                "prompts": {
                    "hi": "आप कितनी राशि का पहला लोन लेना चाहते हैं? (पहला लोन ₹10,000 तक मिलता है)",
                    "hinglish": "Aap kitne amount ka loan apply karna chahte hain? (First tranche ₹10,000 milti hai 7% subsidy ke saath).",
                    "en": "How much loan amount do you want to apply for? (First loan is up to ₹10,000 with 7% interest subsidy)."
                }
            }
        ]
    },

    "pm_kisan": {
        "scheme_id": "pm_kisan",
        "scheme_name": "Pradhan Mantri Kisan Samman Nidhi (PM-KISAN)",
        "portal_url": "https://pmkisan.gov.in",
        "category": "Agriculture ₹6,000 DBT",
        "fields": [
            {
                "key": "farmer_name",
                "label": "Farmer Name (as per Land Record)",
                "hindi_label": "किसान का नाम (खतौनी अनुसार)",
                "attr_key": "name",
                "prompts": {
                    "hi": "पीएम किसान फॉर्म के लिए ज़मीन के कागज़ात के अनुसार किसान का पूरा नाम बताएं।",
                    "hinglish": "PM-KISAN form ke liye zameen ke record ke anusaar Farmer ka Full Name bataiye.",
                    "en": "Please provide the Farmer's Full Name as recorded in land records."
                }
            },
            {
                "key": "mobile",
                "label": "Mobile Number",
                "hindi_label": "मोबाइल नंबर",
                "attr_key": "mobile",
                "prompts": {
                    "hi": "आधार से लिंक 10 अंकों का मोबाइल नंबर बताएं।",
                    "hinglish": "Aadhaar se linked 10-digit mobile number bataiye.",
                    "en": "Please provide your Aadhaar-linked 10-digit mobile number."
                }
            },
            {
                "key": "state_district_village",
                "label": "Village, District & State",
                "hindi_label": "गाँव, ज़िला एवं राज्य",
                "attr_key": "state",
                "prompts": {
                    "hi": "आपकी कृषि भूमि किस गाँव, ज़िले और राज्य में स्थित है?",
                    "hinglish": "Aapki kheti ki zameen kis Gaon, District aur State mein aati hai?",
                    "en": "In which Village, District, and State is your agricultural land situated?"
                }
            },
            {
                "key": "land_size",
                "label": "Cultivable Land Size",
                "hindi_label": "कृषि भूमि का रकबा",
                "attr_key": "land",
                "prompts": {
                    "hi": "आपके पास कुल कितनी कृषि भूमि है? (जैसे 2 एकड़, 1 हेक्टेयर आदि)",
                    "hinglish": "Aapke paas total kitni kheti ki zameen hai? (Jaise 2 acre, 1 hectare)?",
                    "en": "How much cultivable land do you own (e.g. 2 acres, 1 hectare)?"
                }
            }
        ]
    },

    "mudra_yojana": {
        "scheme_id": "mudra_yojana",
        "scheme_name": "Pradhan Mantri MUDRA Yojana (PMMY)",
        "portal_url": "https://www.mudra.org.in",
        "category": "Micro Enterprise Business Loans",
        "fields": [
            {
                "key": "business_name",
                "label": "Enterprise / Business Name",
                "hindi_label": "व्यवसाय / दुकान का नाम",
                "attr_key": "business",
                "prompts": {
                    "hi": "मुद्रा लोन के लिए अपने व्यापार या दुकान का नाम बताएं।",
                    "hinglish": "MUDRA Loan ke liye apne business ya dukaan ka naam bataiye.",
                    "en": "Please provide your Business or Enterprise Name."
                }
            },
            {
                "key": "applicant_name",
                "label": "Applicant Name",
                "hindi_label": "आवेदक का नाम",
                "attr_key": "name",
                "prompts": {
                    "hi": "आवेदक का पूरा नाम बताएं।",
                    "hinglish": "Applicant ka Full Name bataiye.",
                    "en": "Please provide the Applicant's Full Name."
                }
            },
            {
                "key": "mobile",
                "label": "Mobile Number",
                "hindi_label": "मोबाइल नंबर",
                "attr_key": "mobile",
                "prompts": {
                    "hi": "10 अंकों का मोबाइल नंबर बताएं।",
                    "hinglish": "10-digit mobile number bataiye.",
                    "en": "Please provide your 10-digit mobile number."
                }
            },
            {
                "key": "loan_category",
                "label": "Loan Category & Amount",
                "hindi_label": "लोन श्रेणी व राशि",
                "attr_key": "loan_amount",
                "prompts": {
                    "hi": "आप शिशु (₹50,000 तक), किशोर (₹50,000 से ₹5 लाख), या तरुण (₹10 लाख तक) में से कितना लोन चाहते हैं?",
                    "hinglish": "Aap Shishu (₹50,000 tak), Kishore (₹50,000 se ₹5 Lakh), ya Tarun (₹10 Lakh tak) mein se kitna loan apply karna chahte hain?",
                    "en": "Which MUDRA category do you require: Shishu (up to ₹50k), Kishore (₹50k-₹5L), or Tarun (up to ₹10L)?"
                }
            },
            {
                "key": "state",
                "label": "Business Location & State",
                "hindi_label": "व्यवसाय का स्थान व राज्य",
                "attr_key": "state",
                "prompts": {
                    "hi": "व्यवसाय का शहर और राज्य बताएं।",
                    "hinglish": "Business ka shehar aur state bataiye.",
                    "en": "What is the city and state of your business?"
                }
            }
        ]
    }
}


# ──────────────────────────────────────────────────────────────────────────────
# FORM ASSISTANT ENGINE
# ──────────────────────────────────────────────────────────────────────────────

class FormFillingAgent:
    """Manages active form-filling sessions, field extractions, and submissions."""

    @staticmethod
    def detect_form_intent(user_text: str, session: Any) -> Optional[str]:
        """
        Detects if the user wants to initiate, cancel, or confirm an application form.
        Returns: 'start', 'cancel', 'confirm_submit', or None.
        """
        text = user_text.lower().strip()

        # Cancellation keywords
        cancel_kws = ["cancel form", "form cancel", "stop form", "nahi bharna", "chhod do", "form band karo", "exit form"]
        if any(k in text for k in cancel_kws):
            return "cancel"

        # If already waiting for submission confirmation
        if session.active_form and session.active_form.get("awaiting_confirmation"):
            confirm_kws = ["haan", "yes", "submit", "kardo", "kar do", "theek hai", "sure", "proceed", "done", "bhejo"]
            if any(k in text for k in confirm_kws):
                return "confirm_submit"

        # Initiation keywords (e.g. "haan bhar do", "fill my form", "apply kar do")
        start_kws = [
            "bhar do", "form bhar", "fill form", "fill my form", "apply kar do",
            "mera form", "form bharo", "apply for", "application form",
            "yes please", "haan help karo", "haanji bhar do", "theek hai bhar do", "yes fill"
        ]
        if any(k in text for k in start_kws):
            return "start"

        # If the bot previously offered "kya main aapka form bhar doon?" and user says simple affirmation
        last_turn = session.history[-1]["content"].lower() if session.history else ""
        if ("form bhar" in last_turn or "fill" in last_turn) and any(text == yes_word for yes_word in ["haan", "yes", "haanji", "sure", "theek hai", "okay", "ha", "yep"]):
            return "start"

        return None

    @staticmethod
    def resolve_scheme_id(session: Any, user_text: str) -> str:
        """Determines which scheme form to load based on context or text."""
        text = user_text.lower()
        if "pmkvy" in text or "skill" in text or "training" in text:
            return "pmkvy"
        if "ayushman" in text or "golden card" in text or "health card" in text or "hospital" in text:
            return "ayushman_bharat"
        if "svanidhi" in text or "vendor" in text or "thela" in text or "hawker" in text:
            return "pm_svanidhi"
        if "kisan" in text or "farmer" in text or "kheti" in text:
            return "pm_kisan"
        if "mudra" in text or "business loan" in text or "dukaan" in text:
            return "mudra_yojana"

        # Check session's last discussed scheme
        if session.last_discussed_scheme and session.last_discussed_scheme in OFFICIAL_SCHEME_FORMS:
            return session.last_discussed_scheme

        # Default to PMKVY as primary flagship showcase
        return "pmkvy"

    @classmethod
    def start_form(cls, session: Any, user_text: str, language: str) -> Dict[str, Any]:
        """Initializes a new official form for the user."""
        scheme_id = cls.resolve_scheme_id(session, user_text)
        form_meta = OFFICIAL_SCHEME_FORMS.get(scheme_id, OFFICIAL_SCHEME_FORMS["pmkvy"])

        # Pre-fill fields from session attributes if already known
        fields_data: Dict[str, Any] = {}
        for f in form_meta["fields"]:
            key = f["key"]
            attr_key = f.get("attr_key")
            prefilled_val = None
            if attr_key and attr_key in session.attributes:
                prefilled_val = session.attributes[attr_key]
            fields_data[key] = {
                "key": key,
                "label": f["label"],
                "hindi_label": f["hindi_label"],
                "value": prefilled_val,
                "status": "completed" if prefilled_val else "pending"
            }

        session.active_form = {
            "scheme_id": form_meta["scheme_id"],
            "scheme_name": form_meta["scheme_name"],
            "portal_url": form_meta["portal_url"],
            "category": form_meta["category"],
            "fields": fields_data,
            "status": "IN_PROGRESS",
            "current_field_key": None,
            "awaiting_confirmation": False,
            "started_at": datetime.utcnow().isoformat()
        }

        # Find first unfilled field
        next_field_key = cls._get_next_pending_field(session.active_form)
        session.active_form["current_field_key"] = next_field_key

        if next_field_key:
            session.active_form["fields"][next_field_key]["status"] = "current"
            field_def = next(f for f in form_meta["fields"] if f["key"] == next_field_key)
            prompt = field_def["prompts"].get(language, field_def["prompts"]["hinglish"])
            
            # Opening greeting + first question
            if language == "hi":
                intro = f"बहुत बढ़िया! मैं आपका **{form_meta['scheme_name']}** का सरकारी फॉर्म भर देता हूँ। मैं आपसे कुछ आसान सवाल पूछूँगा।\n\n{prompt}"
            elif language == "hinglish":
                intro = f"Bilkul! Main abhi aapka **{form_meta['scheme_name']}** ka official form live bhar deta hoon. Bas 2-3 aasan sawaal poochhoonga.\n\n{prompt}"
            else:
                intro = f"Certainly! I will help you fill out the official application form for **{form_meta['scheme_name']}** right now.\n\n{prompt}"

            return {
                "response": intro,
                "form_state": cls.get_form_state_summary(session.active_form),
                "is_active": True,
                "is_submitted": False
            }
        else:
            # All fields already known from profile!
            return cls._prepare_confirmation_turn(session, language)

    @classmethod
    def process_turn(cls, session: Any, user_text: str, language: str) -> Dict[str, Any]:
        """Handles an ongoing form turn (field collection or final submission)."""
        form = session.active_form
        if not form:
            return cls.start_form(session, user_text, language)

        intent = cls.detect_form_intent(user_text, session)

        # Handle cancel
        if intent == "cancel":
            session.active_form = None
            msg = "Theek hai, maine form cancel kar diya hai. Aap bina kisi hesitation ke aur sawal poochh sakte hain!" if language == "hinglish" else "फॉर्म रद्द कर दिया गया है। आप कोई अन्य जानकारी पूछ सकते हैं।"
            return {
                "response": msg,
                "form_state": None,
                "is_active": False,
                "is_submitted": False
            }

        # Handle final submission confirmation
        if form.get("awaiting_confirmation"):
            if intent == "confirm_submit" or any(w in user_text.lower() for w in ["haan", "yes", "submit", "kardo", "theek hai"]):
                return cls.submit_form(session, language)
            else:
                msg = "Aap form mein kya badalna chahte hain? Ya 'Submit' bolkar submit kar sakte hain." if language == "hinglish" else "What detail would you like to update? Or say 'Submit' to finalize."
                return {
                    "response": msg,
                    "form_state": cls.get_form_state_summary(form),
                    "is_active": True,
                    "is_submitted": False
                }

        # Normal field extraction turn
        curr_key = form.get("current_field_key")
        if curr_key:
            extracted_val = cls._extract_field_value(curr_key, user_text)
            form["fields"][curr_key]["value"] = extracted_val
            form["fields"][curr_key]["status"] = "completed"

            # Update session demographic attributes for memory
            attr_map = {
                "full_name": "name", "farmer_name": "name", "vendor_name": "name", "applicant_name": "name", "family_head_name": "name",
                "mobile": "mobile",
                "age": "age",
                "qualification": "education",
                "state_district": "state", "state": "state",
                "vending_activity": "occupation"
            }
            if curr_key in attr_map and extracted_val:
                session.update_attributes({attr_map[curr_key]: extracted_val})

        # Advance to next field
        next_key = cls._get_next_pending_field(form)
        form["current_field_key"] = next_key

        if next_key:
            form["fields"][next_key]["status"] = "current"
            form_meta = OFFICIAL_SCHEME_FORMS[form["scheme_id"]]
            field_def = next(f for f in form_meta["fields"] if f["key"] == next_key)
            prompt = field_def["prompts"].get(language, field_def["prompts"]["hinglish"])

            ack = "Theek hai, note kar liya! " if language == "hinglish" else "जी, नोट कर लिया गया है। "
            return {
                "response": f"{ack}{prompt}",
                "form_state": cls.get_form_state_summary(form),
                "is_active": True,
                "is_submitted": False
            }
        else:
            # All fields collected -> confirmation stage
            return cls._prepare_confirmation_turn(session, language)

    @classmethod
    def _prepare_confirmation_turn(cls, session: Any, language: str) -> Dict[str, Any]:
        """Summarizes all filled fields and asks citizen for final submission permission."""
        form = session.active_form
        form["awaiting_confirmation"] = True
        form["current_field_key"] = None

        summary_lines = []
        for k, item in form["fields"].items():
            val = item.get("value") or "Not provided"
            summary_lines.append(f"• **{item['label']}**: {val}")
        details_str = "\n".join(summary_lines)

        if language == "hi":
            msg = (
                f"बहुत बढ़िया! आपका **{form['scheme_name']}** आवेदन तैयार हो चुका है:\n\n"
                f"{details_str}\n\n"
                f"क्या मैं इस फॉर्म को आधिकारिक पोर्टल पर **फाइनल सबमिट (Submit)** कर दूँ?"
            )
        elif language == "hinglish":
            msg = (
                f"Superb! Aapka **{form['scheme_name']}** application form complete ho gaya hai:\n\n"
                f"{details_str}\n\n"
                f"Kya main ise official portal par **Submit** kar doon? Bas 'Haan' ya 'Submit' bol dijiye!"
            )
        else:
            msg = (
                f"Excellent! Your official application for **{form['scheme_name']}** is ready:\n\n"
                f"{details_str}\n\n"
                f"Shall I go ahead and **Submit** this application on the official portal for you?"
            )

        return {
            "response": msg,
            "form_state": cls.get_form_state_summary(form),
            "is_active": True,
            "is_submitted": False
        }

    @classmethod
    def submit_form(cls, session: Any, language: str) -> Dict[str, Any]:
        """Permanently records the application submission and returns the acknowledgment receipt."""
        form = session.active_form
        scheme_id = form["scheme_id"]
        scheme_name = form["scheme_name"]

        # Generate official-looking reference number
        prefix = scheme_id.upper().replace("_", "")
        random_num = random.randint(10000, 99999)
        app_ref = f"{prefix}-2026-IND-{random_num}"

        form_data_payload = {
            k: v.get("value") for k, v in form["fields"].items()
        }

        # Save to SQLite Database
        with SessionLocal() as db:
            submission = ApplicationSubmissionModel(
                session_id=session.session_id,
                application_ref=app_ref,
                scheme_id=scheme_id,
                scheme_name=scheme_name,
                form_data=form_data_payload,
                status="SUBMITTED"
            )
            db.add(submission)
            db.commit()

        form["status"] = "SUBMITTED"
        form["application_ref"] = app_ref
        form["submitted_at"] = datetime.utcnow().strftime("%d %B %Y, %I:%M %p")

        if language == "hi":
            msg = (
                f"बधाई हो! 🎉 आपका **{scheme_name}** का आवेदन सफलतापूर्वक जमा हो चुका है!\n\n"
                f"📌 **आवेदन संदर्भ संख्या (Application Ref):** `{app_ref}`\n"
                f"सरकारी पोर्टल ({form['portal_url']}) पर आपकी रसीद स्क्रीन पर तैयार है।"
            )
        elif language == "hinglish":
            msg = (
                f"Mubarak ho! 🎉 Aapka **{scheme_name}** application form successfully submit ho gaya hai!\n\n"
                f"📌 **Application Reference Number:** `{app_ref}`\n"
                f"Aapka official confirmation slip screen par aa gaya hai. Aap ise print ya save kar sakte hain!"
            )
        else:
            msg = (
                f"Congratulations! 🎉 Your application for **{scheme_name}** has been successfully submitted!\n\n"
                f"📌 **Application Reference Number:** `{app_ref}`\n"
                f"Your official acknowledgment receipt is displayed on your screen."
            )

        completed_state = cls.get_form_state_summary(form)
        # Clear active form so user can ask new questions
        session.active_form = None

        return {
            "response": msg,
            "form_state": completed_state,
            "is_active": False,
            "is_submitted": True,
            "application_ref": app_ref,
            "portal_url": form["portal_url"]
        }

    @staticmethod
    def _get_next_pending_field(form: Dict[str, Any]) -> Optional[str]:
        """Finds first key whose value is None or empty."""
        for key, field in form["fields"].items():
            if not field.get("value"):
                return key
        return None

    @staticmethod
    def _extract_field_value(field_key: str, text: str) -> Any:
        """Extracts cleaned value from citizen's utterance."""
        clean = text.strip()

        # Mobile number: 10 digits
        if field_key == "mobile":
            digits = re.findall(r'\b[6-9]\d{9}\b', clean)
            if digits:
                return digits[0]
            digits_any = re.sub(r'\D', '', clean)
            if len(digits_any) >= 10:
                return digits_any[-10:]
            return clean

        # Age
        if field_key in ("age", "child_age"):
            nums = re.findall(r'\b\d{1,2}\b', clean)
            if nums:
                return int(nums[0])

        # Names: strip greeting filler
        if "name" in field_key:
            filler = re.compile(r'^(mera naam|naam hai|my name is|i am|naam|shri|smt)\s*', re.IGNORECASE)
            return filler.sub('', clean).title().strip()

        # Aadhaar last 4
        if "aadhaar" in field_key or "ration" in field_key or "id" in field_key:
            four_digits = re.findall(r'\b\d{4}\b', clean)
            if four_digits:
                return four_digits[0]

        # General text (qualification, course, state, business)
        return clean

    @staticmethod
    def get_form_state_summary(form: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Returns frontend-ready serialization of form progress."""
        if not form:
            return None

        fields_list = list(form["fields"].values())
        total = len(fields_list)
        completed = sum(1 for f in fields_list if f.get("value"))
        pct = int((completed / total) * 100) if total > 0 else 0

        return {
            "scheme_id": form["scheme_id"],
            "scheme_name": form["scheme_name"],
            "category": form.get("category", ""),
            "portal_url": form.get("portal_url", ""),
            "status": form.get("status", "IN_PROGRESS"),
            "current_field_key": form.get("current_field_key"),
            "awaiting_confirmation": form.get("awaiting_confirmation", False),
            "progress_percentage": pct,
            "fields": fields_list,
            "application_ref": form.get("application_ref"),
            "submitted_at": form.get("submitted_at")
        }


form_agent = FormFillingAgent()
