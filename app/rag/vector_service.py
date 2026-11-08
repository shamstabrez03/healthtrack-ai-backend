"""
Unified Vector Database Service — Supabase pgvector with ChromaDB fallback.

Uses Google Gemini (models/text-embedding-004, 768-dim) for semantic vectors.
When connected to Supabase/PostgreSQL, embeddings are persisted in the `report_embeddings` table.
Foreign keys provide automatic ON DELETE CASCADE cleanup.
"""

import logging
from typing import List, Dict, Optional, Any
from sqlalchemy.orm import Session
from app.config import settings
from app.ingestion.pdf_parser import PageContent
from app.database.models import ReportEmbedding

logger = logging.getLogger(__name__)


def _is_postgres_active() -> bool:
    """Check if PostgreSQL / Supabase is configured."""
    url = settings.DATABASE_URL or ""
    return url.startswith("postgres") or "supabase" in url or "render.com" in url


def _get_gemini_embeddings(texts: List[str], api_key: str) -> List[List[float]]:
    """Generate 768-dimensional embeddings using Gemini text-embedding-004."""
    import google.generativeai as genai
    genai.configure(api_key=api_key)

    embeddings = []
    # Batch embeddings
    for text in texts:
        clean_text = text[:8000].strip()
        if not clean_text:
            continue
        try:
            res = genai.embed_content(
                model="models/text-embedding-004",
                content=clean_text,
                task_type="retrieval_document",
            )
            embeddings.append(res["embedding"])
        except Exception as e:
            logger.warning(f"Failed to generate embedding for chunk: {e}")
            embeddings.append(None)
    return embeddings


def _get_query_embedding(query: str, api_key: str) -> Optional[List[float]]:
    """Generate query embedding using Gemini text-embedding-004."""
    import google.generativeai as genai
    genai.configure(api_key=api_key)

    try:
        res = genai.embed_content(
            model="models/text-embedding-004",
            content=query[:2000],
            task_type="retrieval_query",
        )
        return res["embedding"]
    except Exception as e:
        logger.warning(f"Failed to generate query embedding: {e}")
        return None


class VectorService:
    """Vector storage and semantic search service."""

    def index_report(
        self,
        report_id: str,
        patient_id: str,
        pages: List[PageContent],
        report_metadata: Dict[str, str],
        observations: List[Dict[str, Any]],
        api_key: str,
        db: Optional[Session] = None,
    ):
        """Index report content into Supabase pgvector (or ChromaDB fallback)."""
        # If PostgreSQL and db session provided, use Supabase pgvector
        if _is_postgres_active() and db is not None:
            try:
                self._index_in_supabase(db, report_id, patient_id, pages, report_metadata, observations, api_key)
                return
            except Exception as e:
                logger.warning(f"Supabase pgvector indexing failed, trying Chroma fallback: {e}")

        # Fallback to local ChromaDB
        try:
            from app.rag.chroma import chroma_service
            chroma_service.index_report(report_id, patient_id, pages, report_metadata, observations, api_key)
        except Exception as e:
            logger.warning(f"ChromaDB fallback indexing failed: {e}")

    def _index_in_supabase(
        self,
        db: Session,
        report_id: str,
        patient_id: str,
        pages: List[PageContent],
        report_metadata: Dict[str, str],
        observations: List[Dict[str, Any]],
        api_key: str,
    ):
        """Persist embeddings directly into Supabase report_embeddings table."""
        chunks = []

        # 1. Page-level chunks
        for page in pages:
            if not page.text.strip():
                continue
            chunks.append({
                "text": page.text[:8000],
                "chunk_type": "page",
                "page_number": page.page_number,
                "panel": None,
            })

        # 2. Observation panel summaries
        panels = {}
        for obs in observations:
            p = obs.get("panel") or "General"
            panels.setdefault(p, []).append(obs)

        for panel_name, panel_obs in panels.items():
            lines = [f"Panel: {panel_name}"]
            for obs in panel_obs:
                l = f"{obs.get('test_name', '?')}: {obs.get('value_text', '?')}"
                if obs.get("unit"):
                    l += f" {obs['unit']}"
                if obs.get("reference_text"):
                    l += f" (ref: {obs['reference_text']})"
                lines.append(l)
            chunks.append({
                "text": "\n".join(lines),
                "chunk_type": "panel_summary",
                "page_number": None,
                "panel": panel_name,
            })

        if not chunks:
            return

        # Generate vectors via Gemini
        texts = [c["text"] for c in chunks]
        embeddings = _get_gemini_embeddings(texts, api_key)

        # Remove existing embeddings for this report if any
        db.query(ReportEmbedding).filter(ReportEmbedding.report_id == report_id).delete()

        # Insert new embeddings
        records = []
        for chunk, emb in zip(chunks, embeddings):
            if emb is None:
                continue
            records.append(ReportEmbedding(
                report_id=report_id,
                patient_id=patient_id,
                chunk_text=chunk["text"],
                chunk_type=chunk["chunk_type"],
                page_number=chunk["page_number"],
                panel=chunk["panel"],
                report_type=report_metadata.get("report_type"),
                report_date=str(report_metadata.get("report_date", "")),
                laboratory=report_metadata.get("laboratory"),
                embedding=emb,
            ))

        if records:
            db.bulk_save_objects(records)
            db.commit()
            logger.info(f"Indexed {len(records)} pgvector embeddings in Supabase for report {report_id}")

    def search(
        self,
        query: str,
        patient_id: str,
        report_id: Optional[str] = None,
        n_results: int = 10,
        api_key: Optional[str] = None,
        db: Optional[Session] = None,
    ) -> List[Dict]:
        """Search vector embeddings in Supabase pgvector (or ChromaDB fallback)."""
        # Try Supabase pgvector first
        if _is_postgres_active() and db is not None and api_key:
            try:
                results = self._search_supabase(db, query, patient_id, report_id, n_results, api_key)
                if results:
                    return results
            except Exception as e:
                logger.warning(f"Supabase pgvector search failed, falling back to Chroma: {e}")

        # ChromaDB fallback
        try:
            from app.rag.chroma import chroma_service
            return chroma_service.search(query, patient_id, report_id=report_id, n_results=n_results)
        except Exception as e:
            logger.warning(f"ChromaDB search fallback failed: {e}")
            return []

    def _search_supabase(
        self,
        db: Session,
        query: str,
        patient_id: str,
        report_id: Optional[str],
        n_results: int,
        api_key: str,
    ) -> List[Dict]:
        """Perform cosine distance similarity search in Supabase."""
        query_vec = _get_query_embedding(query, api_key)
        if not query_vec:
            return []

        # Cosine distance similarity
        similarity_expr = (1 - ReportEmbedding.embedding.cosine_distance(query_vec))

        q = db.query(
            ReportEmbedding,
            similarity_expr.label("similarity"),
        ).filter(ReportEmbedding.patient_id == patient_id)

        if report_id:
            q = q.filter(ReportEmbedding.report_id == report_id)

        rows = q.order_by(ReportEmbedding.embedding.cosine_distance(query_vec)).limit(n_results).all()

        formatted = []
        for emb, sim in rows:
            formatted.append({
                "text": emb.chunk_text,
                "metadata": {
                    "report_id": emb.report_id,
                    "patient_id": emb.patient_id,
                    "report_date": emb.report_date,
                    "report_type": emb.report_type,
                    "laboratory": emb.laboratory,
                    "page_number": emb.page_number,
                    "chunk_type": emb.chunk_type,
                    "panel": emb.panel,
                },
                "distance": 1.0 - float(sim) if sim is not None else None,
                "report_id": emb.report_id,
                "report_date": emb.report_date,
                "report_type": emb.report_type,
                "page_number": emb.page_number,
            })
        return formatted

    def delete_report_data(self, report_id: str, db: Optional[Session] = None):
        """Delete report embeddings."""
        if db is not None:
            try:
                db.query(ReportEmbedding).filter(ReportEmbedding.report_id == report_id).delete()
                db.commit()
            except Exception as e:
                logger.warning(f"Failed to delete pgvector embeddings for report {report_id}: {e}")

        try:
            from app.rag.chroma import chroma_service
            chroma_service.delete_report_data(report_id)
        except Exception:
            pass

    def delete_patient_data(self, patient_id: str, db: Optional[Session] = None):
        """Delete all patient embeddings."""
        if db is not None:
            try:
                db.query(ReportEmbedding).filter(ReportEmbedding.patient_id == patient_id).delete()
                db.commit()
            except Exception as e:
                logger.warning(f"Failed to delete pgvector embeddings for patient {patient_id}: {e}")

        try:
            from app.rag.chroma import chroma_service
            chroma_service.delete_patient_data(patient_id)
        except Exception:
            pass


vector_service = VectorService()
