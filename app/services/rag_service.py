import logging
from pathlib import Path

import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer

from app.config import (
    CHROMA_PERSIST_DIR,
    DATA_DIR,
    EMBEDDING_MODEL,
    CHUNK_SIZE,
    CHUNK_OVERLAP,
    TOP_K_RESULTS,
)

logger = logging.getLogger(__name__)

COLLECTION_NAME = "medical_knowledge_v2"

METADATA_FIELDS = (
    "disease", "icd10", "category", "urgency", "specialist",
    "who_guideline", "cdc_mapping", "pubmed_references",
)


class RAGService:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        logger.info("Initializing RAG service (lightweight, lazy embeddings)...")

        # ✅ Lazy-loaded model (keep this)
        self.embedding_model = None

        # ✅ Chroma client (NO default embedding)
        self.chroma_client = chromadb.Client(
            Settings(
                anonymized_telemetry=False,
                persist_directory=CHROMA_PERSIST_DIR,
                is_persistent=True,
            )
        )

        # 🔥 CRITICAL FIX:
        # embedding_function=None prevents Chroma from loading ONNX
        self.collection = self.chroma_client.get_or_create_collection(
            name=COLLECTION_NAME,
            embedding_function=None,
            metadata={"hnsw:space": "cosine"},
        )

        if self.collection.count() == 0:
            logger.info("Vector DB empty — will ingest on first use")
        else:
            logger.info(
                f"Vector DB ready: {self.collection.count()} chunks "
                f"in collection '{COLLECTION_NAME}'"
            )

        self._initialized = True

    # =========================
    # Lazy loading
    # =========================
    def _load_embedding_model(self):
        if self.embedding_model is None:
            logger.info("Loading embedding model (lazy)...")
            self.embedding_model = SentenceTransformer(
                EMBEDDING_MODEL,
                device="cpu",
            )

    # =========================
    # Helpers
    # =========================
    def _chunk_text(self, text: str) -> list[str]:
        words = text.split()
        chunks = []
        start = 0
        while start < len(words):
            end = start + CHUNK_SIZE
            chunks.append(" ".join(words[start:end]))
            start += CHUNK_SIZE - CHUNK_OVERLAP
        return chunks

    def _parse_disease_blocks(self, text: str) -> list[dict]:
        blocks = text.split("---")
        parsed = []

        for block in blocks:
            block = block.strip()
            if not block:
                continue

            metadata = {}
            for line in block.split("\n"):
                if ":" in line:
                    key, _, value = line.partition(":")
                    key = key.strip().lower()
                    value = value.strip()
                    if key in METADATA_FIELDS:
                        metadata[key] = value

            parsed.append({"text": block, "metadata": metadata})

        return parsed

    # =========================
    # Ingestion
    # =========================
    def _ingest_knowledge_base(self):
        logger.info("Building medical knowledge vector DB...")
        data_dir = Path(DATA_DIR)

        if not data_dir.exists():
            logger.warning(f"Data directory not found: {data_dir}")
            return

        self._load_embedding_model()

        all_chunks = []
        all_ids = []
        all_metadatas = []

        doc_id = 0
        disease_count = 0

        for filepath in sorted(data_dir.glob("*.txt")):
            logger.info(f"Processing {filepath.name}")
            text = filepath.read_text(encoding="utf-8")
            disease_blocks = self._parse_disease_blocks(text)

            for disease_block in disease_blocks:
                disease_count += 1
                chunks = self._chunk_text(disease_block["text"])

                for i, chunk in enumerate(chunks):
                    all_chunks.append(chunk)
                    all_ids.append(f"med_{doc_id}")

                    meta = {
                        "source": filepath.name,
                        "chunk_index": i,
                        "total_chunks": len(chunks),
                    }

                    for field in METADATA_FIELDS:
                        if field in disease_block["metadata"]:
                            val = disease_block["metadata"][field]
                            meta[field] = val[:500] if len(val) > 500 else val

                    all_metadatas.append(meta)
                    doc_id += 1

        if not all_chunks:
            logger.warning("No documents found to ingest")
            return

        logger.info(f"Encoding {len(all_chunks)} chunks...")
        embeddings = self.embedding_model.encode(
            all_chunks,
            show_progress_bar=True,
        ).tolist()

        batch_size = 100
        for i in range(0, len(all_chunks), batch_size):
            end = min(i + batch_size, len(all_chunks))
            self.collection.add(
                ids=all_ids[i:end],
                documents=all_chunks[i:end],
                embeddings=embeddings[i:end],
                metadatas=all_metadatas[i:end],
            )

        logger.info(
            f"Vector DB built: {len(all_chunks)} chunks "
            f"from {disease_count} diseases"
        )

    # =========================
    # Retrieval
    # =========================
    def retrieve(self, query: str, top_k: int | None = None) -> list[dict]:
        if self.collection.count() == 0:
            self._ingest_knowledge_base()

        self._load_embedding_model()

        k = top_k or TOP_K_RESULTS
        query_embedding = self.embedding_model.encode([query]).tolist()

        results = self.collection.query(
            query_embeddings=query_embedding,
            n_results=k,
            include=["documents", "metadatas", "distances"],
        )

        retrieved = []
        if results and results["documents"]:
            for doc, meta, dist in zip(
                results["documents"][0],
                results["metadatas"][0],
                results["distances"][0],
            ):
                retrieved.append({
                    "content": doc,
                    "metadata": meta,
                    "relevance_score": 1 - dist,
                })

        return retrieved

    # =========================
    # Context builder
    # =========================
    def build_context(self, symptoms: list[str], additional_info: str = "") -> str:
        query = f"Patient symptoms: {', '.join(symptoms)}. {additional_info}"
        results = self.retrieve(query)

        if not results:
            return "No relevant medical knowledge found."

        parts = []
        for i, r in enumerate(results, 1):
            meta = r["metadata"]
            parts.append(
                f"[Reference {i}] Disease: {meta.get('disease', 'Unknown')} "
                f"| Relevance: {r['relevance_score']:.2f}\n{r['content']}"
            )

        return "\n\n".join(parts)

    def get_stats(self) -> dict:
        return {
            "collection": COLLECTION_NAME,
            "total_chunks": self.collection.count(),
            "embedding_model": EMBEDDING_MODEL,
            "persist_directory": CHROMA_PERSIST_DIR,
        }


def get_rag_service() -> RAGService:
    return RAGService()
