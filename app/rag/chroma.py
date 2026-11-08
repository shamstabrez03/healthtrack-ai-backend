"""ChromaDB service — document indexing, retrieval, and cleanup."""

import logging
from typing import List, Dict, Optional, Any
from app.config import settings
from app.ingestion.pdf_parser import PageContent

logger = logging.getLogger(__name__)

# Lazy-initialized ChromaDB client
_client = None
_collection = None
COLLECTION_NAME = "medical_reports"


def _get_client():
    global _client
    if _client is None:
        import chromadb
        from chromadb.config import Settings as ChromaSettings
        _client = chromadb.PersistentClient(
            path=settings.CHROMA_PERSIST_DIR,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
    return _client


def _get_collection():
    global _collection
    if _collection is None:
        client = _get_client()
        _collection = client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
    return _collection


class ChromaService:
    """Manages ChromaDB operations for medical report documents."""

    def index_report(
        self,
        report_id: str,
        patient_id: str,
        pages: List[PageContent],
        report_metadata: Dict[str, str],
        observations: List[Dict[str, Any]],
        api_key: str,
    ):
        """
        Index report content into ChromaDB with rich metadata.
        Creates chunks per page and per observation group.
        """
        collection = _get_collection()

        documents = []
        metadatas = []
        ids = []

        # 1. Index page-level chunks
        for page in pages:
            if not page.text.strip():
                continue

            doc_id = f"{report_id}_page_{page.page_number}"
            documents.append(page.text[:8000])  # Limit chunk size
            metadatas.append({
                "patient_id": patient_id,
                "report_id": report_id,
                "report_date": report_metadata.get("report_date", ""),
                "report_type": report_metadata.get("report_type", ""),
                "laboratory": report_metadata.get("laboratory", ""),
                "page_number": page.page_number,
                "chunk_type": "page",
            })
            ids.append(doc_id)

        # 2. Index observation summaries (grouped by panel)
        panels = {}
        for obs in observations:
            panel = obs.get("panel") or "General"
            if panel not in panels:
                panels[panel] = []
            panels[panel].append(obs)

        for panel_name, panel_obs in panels.items():
            summary_parts = [f"Panel: {panel_name}"]
            for obs in panel_obs:
                line = f"{obs.get('test_name', '?')}: {obs.get('value_text', '?')}"
                if obs.get("unit"):
                    line += f" {obs['unit']}"
                if obs.get("reference_text"):
                    line += f" (ref: {obs['reference_text']})"
                summary_parts.append(line)

            doc_id = f"{report_id}_panel_{panel_name.lower().replace(' ', '_')}"
            documents.append("\n".join(summary_parts))
            metadatas.append({
                "patient_id": patient_id,
                "report_id": report_id,
                "report_date": report_metadata.get("report_date", ""),
                "report_type": report_metadata.get("report_type", ""),
                "laboratory": report_metadata.get("laboratory", ""),
                "panel": panel_name,
                "chunk_type": "panel_summary",
            })
            ids.append(doc_id)

        if documents:
            # Add in batches to avoid overwhelming ChromaDB
            batch_size = 50
            for i in range(0, len(documents), batch_size):
                batch_docs = documents[i:i + batch_size]
                batch_metas = metadatas[i:i + batch_size]
                batch_ids = ids[i:i + batch_size]
                collection.upsert(
                    documents=batch_docs,
                    metadatas=batch_metas,
                    ids=batch_ids,
                )

        logger.info(f"Indexed {len(documents)} chunks for report {report_id}")

    def search(
        self,
        query: str,
        patient_id: str,
        report_id: Optional[str] = None,
        n_results: int = 10,
    ) -> List[Dict]:
        """
        Search ChromaDB with mandatory patient_id filtering.
        Optionally scope to a specific report.
        """
        collection = _get_collection()

        where_filter = {"patient_id": patient_id}
        if report_id:
            where_filter = {
                "$and": [
                    {"patient_id": patient_id},
                    {"report_id": report_id},
                ]
            }

        try:
            results = collection.query(
                query_texts=[query],
                n_results=n_results,
                where=where_filter,
                include=["documents", "metadatas", "distances"],
            )
        except Exception as e:
            logger.warning(f"ChromaDB search failed: {e}")
            return []

        # Format results
        formatted = []
        if results and results.get("documents"):
            for i, doc in enumerate(results["documents"][0]):
                meta = results["metadatas"][0][i] if results.get("metadatas") else {}
                distance = results["distances"][0][i] if results.get("distances") else None
                formatted.append({
                    "text": doc,
                    "metadata": meta,
                    "distance": distance,
                    "report_id": meta.get("report_id"),
                    "report_date": meta.get("report_date"),
                    "report_type": meta.get("report_type"),
                    "page_number": meta.get("page_number"),
                })

        return formatted

    def delete_report_data(self, report_id: str):
        """Delete all ChromaDB entries for a specific report."""
        try:
            collection = _get_collection()
            # Get all IDs for this report
            results = collection.get(
                where={"report_id": report_id},
                include=[],
            )
            if results and results.get("ids"):
                collection.delete(ids=results["ids"])
                logger.info(f"Deleted {len(results['ids'])} ChromaDB entries for report {report_id}")
        except Exception as e:
            logger.warning(f"Failed to delete ChromaDB data for report {report_id}: {e}")

    def delete_patient_data(self, patient_id: str):
        """Delete ALL ChromaDB entries for a patient."""
        try:
            collection = _get_collection()
            results = collection.get(
                where={"patient_id": patient_id},
                include=[],
            )
            if results and results.get("ids"):
                collection.delete(ids=results["ids"])
                logger.info(f"Deleted {len(results['ids'])} ChromaDB entries for patient {patient_id}")
        except Exception as e:
            logger.warning(f"Failed to delete ChromaDB data for patient {patient_id}: {e}")


# Singleton
chroma_service = ChromaService()
