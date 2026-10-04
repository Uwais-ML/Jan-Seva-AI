"""
Unit and integration tests for RAG pipeline, multilingual detection, and strict grounding.
"""

import sys
import unittest
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from RAG.Query_writer import detect_language, extract_user_attributes, Query_writer
from RAG.Indegstion import KnowledgeIndexer
from RAG.Retrival import Retrival, GroundedRetriever


class TestRAGPipeline(unittest.TestCase):

    def test_language_detection(self):
        """Test English, Hindi, and Hinglish classification."""
        self.assertEqual(detect_language("What is the eligibility for PMKVY?"), "en")
        self.assertEqual(detect_language("मुझे आयुष्मान भारत के बारे में जानकारी चाहिए"), "hi")
        self.assertEqual(detect_language("mera umar 22 saal hai mujhe job training chahiye"), "hinglish")

    def test_attribute_extraction(self):
        """Test deterministic entity extraction for age, income, and occupation."""
        attrs = extract_user_attributes("Meri age 24 saal hai, annual income 1.5 lakh hai aur main kisan hu")
        self.assertEqual(attrs.get("age"), 24)
        self.assertEqual(attrs.get("annual_income"), 150000.0)
        self.assertEqual(attrs.get("occupation"), "Farmer")

    def test_grounded_retrieval_relevance(self):
        """Relevant queries should retrieve valid scheme chunks."""
        retriever = GroundedRetriever()
        chunks = retriever.search("Ayushman Bharat health insurance 5 lakh")
        self.assertGreater(len(chunks), 0)
        titles = [c.title.lower() for c in chunks]
        self.assertTrue(any("ayushman" in t for t in titles))

    def test_strict_grounding_negative(self):
        """Unrelated queries should not hallucinate and return a natural 'no information' response."""
        r = Retrival()
        res = r.get_grounded_answer("Can you give me a recipe for cooking pizza with pineapple?")
        self.assertEqual(res["retrieved_chunks"], 0)
        # Should express inability to help, not hallucinate a pizza recipe
        answer_lower = res["answer"].lower()
        self.assertTrue(
            "don't have" in answer_lower or "do not have" in answer_lower
            or "nahi" in answer_lower or "not have" in answer_lower,
            f"Expected a 'no information' response, got: {res['answer']}"
        )


if __name__ == "__main__":
    unittest.main()
