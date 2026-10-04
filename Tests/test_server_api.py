"""
In-memory unit tests for Backend REST handlers.
Runs without opening external TCP sockets, compatible with sandbox environments.
"""

import sys
import json
import unittest
from pathlib import Path
from aiohttp.test_utils import make_mocked_request

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from Backend.server import (
    health_handler,
    schemes_handler,
    chat_handler,
    check_eligibility_handler,
    get_session_handler
)
from Database.session import init_db


class TestServerHandlersInMemory(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        init_db()

    async def test_health_handler(self):
        """Verify GET /health response."""
        req = make_mocked_request("GET", "/health")
        resp = await health_handler(req)
        self.assertEqual(resp.status, 200)
        body = json.loads(resp.text)
        self.assertEqual(body["status"], "healthy")

    async def test_schemes_handler(self):
        """Verify GET /api/schemes returns seeded schemes."""
        req = make_mocked_request("GET", "/api/schemes")
        resp = await schemes_handler(req)
        self.assertEqual(resp.status, 200)
        schemes = json.loads(resp.text)
        self.assertGreater(len(schemes), 0)
        ids = [s["scheme_id"] for s in schemes]
        self.assertIn("pmkvy", ids)
        self.assertIn("ayushman_bharat", ids)

    async def test_chat_handler(self):
        """Verify POST /api/chat processes query and returns grounded response."""
        payload = json.dumps({
            "session_id": "test_mem_session",
            "text": "What is PMKVY skill training scheme?"
        }).encode("utf-8")
        req = make_mocked_request("POST", "/api/chat", headers={"Content-Type": "application/json"})
        req._read_bytes = payload
        resp = await chat_handler(req)
        self.assertEqual(resp.status, 200)
        data = json.loads(resp.text)
        self.assertIn("response", data)
        self.assertEqual(data["detected_language"], "en")
        self.assertGreater(len(data["sources"]), 0)

    async def test_check_eligibility_handler(self):
        """Verify POST /api/check-eligibility evaluates rules."""
        payload = json.dumps({
            "session_id": "elig_mem_session",
            "age": 20,
            "occupation": "Unemployed"
        }).encode("utf-8")
        req = make_mocked_request("POST", "/api/check-eligibility", headers={"Content-Type": "application/json"})
        req._read_bytes = payload
        resp = await check_eligibility_handler(req)
        self.assertEqual(resp.status, 200)
        data = json.loads(resp.text)
        self.assertIn("results", data)
        eligible = [r for r in data["results"] if r["is_eligible"]]
        self.assertGreater(len(eligible), 0)


    async def test_telephony_incoming_handler(self):
        """Verify GET/POST /api/telephony/incoming returns valid TwiML with Hindi voice."""
        from Backend.telephony_twilio import twilio_incoming_call_handler
        req = make_mocked_request("POST", "/api/telephony/incoming")
        resp = await twilio_incoming_call_handler(req)
        self.assertEqual(resp.status, 200)
        self.assertIn("Response", resp.text)
        self.assertIn("Gather", resp.text)
        self.assertIn("hi-IN", resp.text)


if __name__ == "__main__":
    unittest.main()
