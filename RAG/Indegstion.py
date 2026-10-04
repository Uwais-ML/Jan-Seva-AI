"""
Document Ingestion pipeline for Indian Citizen Welfare & Schemes.
Loads documents from /Documents, performs semantic and parent-child chunking,
and stores them in persistent vector store and docstore.
"""

import os
import sys
import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

logger = logging.getLogger(__name__)

DOCUMENTS_DIR = BASE_DIR / "Documents"
STORAGE_DIR = BASE_DIR / "RAG" / "storage"


class KnowledgeBaseChunk:
    def __init__(self, doc_id: str, title: str, content: str, metadata: Dict[str, Any]):
        self.doc_id = doc_id
        self.title = title
        self.content = content
        self.metadata = metadata

    def to_dict(self) -> Dict[str, Any]:
        return {
            "doc_id": self.doc_id,
            "title": self.title,
            "content": self.content,
            "metadata": self.metadata
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "KnowledgeBaseChunk":
        return cls(
            doc_id=data["doc_id"],
            title=data["title"],
            content=data["content"],
            metadata=data.get("metadata", {})
        )


class KnowledgeIndexer:
    """
    Manages document indexing, metadata tagging, and local retrieval store.
    """

    def __init__(self, storage_dir: Optional[Path] = None):
        self.storage_dir = storage_dir or STORAGE_DIR
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.index_file = self.storage_dir / "knowledge_index.json"
        self.chunks: List[KnowledgeBaseChunk] = []
        self.load_index()

    def load_index(self):
        """Loads chunks from persistent storage if available."""
        if self.index_file.exists():
            try:
                with open(self.index_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.chunks = [KnowledgeBaseChunk.from_dict(item) for item in data]
                logger.info(f"Loaded {len(self.chunks)} knowledge chunks from {self.index_file}")
            except Exception as e:
                logger.error(f"Error loading index: {e}")
                self.chunks = []

    def save_index(self):
        """Saves chunks to disk."""
        with open(self.index_file, "w", encoding="utf-8") as f:
            json.dump([c.to_dict() for c in self.chunks], f, indent=2, ensure_ascii=False)
        logger.info(f"Saved {len(self.chunks)} knowledge chunks to {self.index_file}")

    def ingest_documents(self) -> int:
        """
        Parses all Markdown files and JSON records in Documents/ and builds index.
        """
        chunks: List[KnowledgeBaseChunk] = []

        # 1. Ingest JSON schemes
        json_file = DOCUMENTS_DIR / "schemes_knowledge_base.json"
        if json_file.exists():
            with open(json_file, "r", encoding="utf-8") as f:
                schemes = json.load(f)
                for s in schemes:
                    scheme_id = s.get("scheme_id", "scheme")
                    name = s.get("name", "")
                    content = (
                        f"Scheme: {name}\n"
                        f"Category: {s.get('category')}\n"
                        f"Description: {s.get('description')}\n"
                        f"Eligible Age: {s.get('min_age')} to {s.get('max_age')} years\n"
                        f"Max Annual Income: {s.get('max_annual_income') or 'No strict limit'}\n"
                        f"Target Occupations: {', '.join(s.get('eligible_occupations', []))}\n"
                        f"Applicable States: {', '.join(s.get('eligible_states', ['All']))}\n"
                        f"Benefits: {s.get('benefits')}\n"
                        f"Official Portal: {s.get('portal_url')}\n"
                    )
                    chunks.append(KnowledgeBaseChunk(
                        doc_id=f"json_{scheme_id}",
                        title=name,
                        content=content,
                        metadata={
                            "scheme_id": scheme_id,
                            "category": s.get("category"),
                            "source": "schemes_knowledge_base.json",
                            "tags": s.get("tags", []),
                            "portal_url": s.get("portal_url", "")
                        }
                    ))

        # 2. Ingest Markdown files
        for md_file in DOCUMENTS_DIR.glob("*.md"):
            with open(md_file, "r", encoding="utf-8") as f:
                text = f.read()

            title = md_file.stem.replace("_", " ").title()
            # Split into major sections
            sections = text.split("\n## ")
            parent_title = sections[0].strip("# \n") or title

            for idx, sec in enumerate(sections):
                if not sec.strip():
                    continue
                heading = sec.split("\n")[0] if idx > 0 else "Overview"
                sec_text = f"## {sec}" if idx > 0 else sec
                chunk_id = f"{md_file.stem}_sec_{idx}"
                chunks.append(KnowledgeBaseChunk(
                    doc_id=chunk_id,
                    title=f"{parent_title} - {heading}",
                    content=sec_text.strip(),
                    metadata={
                        "source": md_file.name,
                        "parent_title": parent_title,
                        "section": heading
                    }
                ))

        self.chunks = chunks
        self.save_index()
        return len(self.chunks)


def run_ingestion() -> int:
    """Helper entry point for ingestion."""
    indexer = KnowledgeIndexer()
    count = indexer.ingest_documents()
    print(f"Ingestion complete: {count} knowledge chunks indexed.")
    return count


if __name__ == "__main__":
    run_ingestion()
