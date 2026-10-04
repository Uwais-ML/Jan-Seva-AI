#!/usr/bin/env python3
"""
Jan Seva AI - Quick Phone Call Launcher
Initiates a live test call to a citizen's phone number using your Twilio account.

Usage:
  ./.venv/bin/python3 dial_phone_call.py +91XXXXXXXXXX https://YOUR-NGROK-URL.ngrok-free.app
"""

import sys
import asyncio
import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

from Backend.telephony_twilio import initiate_outbound_call


async def main():
    if len(sys.argv) < 3:
        print("Usage: python3 dial_phone_call.py <PHONE_NUMBER_WITH_COUNTRY_CODE> <PUBLIC_BASE_URL>")
        print("Example: python3 dial_phone_call.py +919876543210 https://abc-123.ngrok-free.app")
        sys.exit(1)

    to_phone = sys.argv[1].strip()
    base_url = sys.argv[2].strip()

    print(f"📞 Initiating AI Phone Call to: {to_phone}")
    print(f"🔗 Using Webhook URL: {base_url}/api/telephony/incoming")

    try:
        result = await initiate_outbound_call(to_phone, base_url)
        print("\n✅ Call status:", result)
        print("Your phone will ring shortly! When answered, the AI assistant will speak in Hindi/English.")
    except Exception as e:
        print("\n❌ Call failed:", e)


if __name__ == "__main__":
    asyncio.run(main())
