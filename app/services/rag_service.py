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
        logger.info("Initializing RAG service with medical vector DB...")
        self.embedding_model = SentenceTransformer(EMBEDDING_MODEL)
        self.chroma_client = chromadb.Client(Settings(
            anonymized_telemetry=False,
            persist_directory=CHROMA_PERSIST_DIR,
            is_persistent=True,
        ))
        self.collection = self.chroma_client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
        if self.collection.count() == 0:
            self._ingest_knowledge_base()
        else:
            logger.info(
                f"Vector DB ready: {self.collection.count()} embedded chunks "
                f"in collection '{COLLECTION_NAME}'"
            )
        self._initialized = True

    def _chunk_text(self, text: str) -> list[str]:
        """Split text into overlapping chunks for embedding."""
        words = text.split()
        chunks = []
        start = 0
        while start < len(words):
            end = start + CHUNK_SIZE
            chunk = " ".join(words[start:end])
            chunks.append(chunk)
            start += CHUNK_SIZE - CHUNK_OVERLAP
        return chunks

    def _parse_disease_blocks(self, text: str) -> list[dict]:
        """Parse structured disease blocks with ICD-10, WHO, CDC, PubMed metadata."""
        blocks = text.split("---")
        parsed = []
        for block in blocks:
            block = block.strip()
            if not block:
                continue
            metadata = {}
            for line in block.split("\n"):
                line = line.strip()
                if ":" in line:
                    key, _, value = line.partition(":")
                    key = key.strip().lower()
                    value = value.strip()
                    if key in METADATA_FIELDS:
                        metadata[key] = value
            parsed.append({"text": block, "metadata": metadata})
        return parsed

    def _ingest_knowledge_base(self):
        """Load medical knowledge files into ChromaDB vector store.

        Sources embedded:
        - Medical textbook-style disease descriptions
        - WHO clinical guidelines and global health data
        - CDC surveillance data and US epidemiology
        - ICD-10 diagnostic codes for standardized classification
        - PubMed references (PMIDs) for evidence-based medicine
        """
        logger.info("Building medical knowledge vector DB...")
        logger.info("Embedding sources: medical guidelines, WHO, CDC, ICD-10, PubMed references")
        data_dir = Path(DATA_DIR)
        if not data_dir.exists():
            logger.warning(f"Data directory not found: {data_dir}")
            return

        all_chunks = []
        all_ids = []
        all_metadatas = []
        doc_id = 0
        disease_count = 0

        for filepath in sorted(data_dir.glob("*.txt")):
            logger.info(f"Processing {filepath.name}...")
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
                        "source_type": "medical_knowledge_base",
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

        logger.info(f"Encoding {len(all_chunks)} chunks from {disease_count} diseases...")
        embeddings = self.embedding_model.encode(
            all_chunks, show_progress_bar=True
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
            f"Vector DB built: {len(all_chunks)} chunks from {disease_count} diseases "
            f"across {len(list(data_dir.glob('*.txt')))} specialty files"
        )

    def retrieve(self, query: str, top_k: int | None = None) -> list[dict]:
        """Semantic search against the medical knowledge vector DB."""
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

    def build_context(self, symptoms: list[str], additional_info: str = "") -> str:
        """Build RAG context from vector DB for the diagnosis engine."""
        query = f"Patient symptoms: {', '.join(symptoms)}. {additional_info}"
        results = self.retrieve(query, top_k=TOP_K_RESULTS)

        if not results:
            return "No relevant medical knowledge found in the vector database."

        context_parts = []
        for i, r in enumerate(results, 1):
            score = r["relevance_score"]
            meta = r["metadata"]
            disease = meta.get("disease", "Unknown")
            icd10 = meta.get("icd10", "")
            source = meta.get("source", "")

            header = f"[Reference {i}] Disease: {disease}"
            if icd10:
                header += f" | ICD-10: {icd10}"
            header += f" | Relevance: {score:.2f} | Source: {source}"

            context_parts.append(f"{header}\n{r['content']}")

        return "\n\n".join(context_parts)

    def get_stats(self) -> dict:
        """Get vector DB statistics."""
        return {
            "collection": COLLECTION_NAME,
            "total_chunks": self.collection.count(),
            "embedding_model": EMBEDDING_MODEL,
            "persist_directory": CHROMA_PERSIST_DIR,
        }


def get_rag_service() -> RAGService:
    return RAGService()
