from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from app.db.session import get_session_factory
from app.embeddings.errors import EmbeddingUnavailableError
from app.embeddings.indexer import index_import_job
from app.embeddings.runtime import set_embedding_status
from app.models.import_job import ImportJob, ImportStatus

logger = logging.getLogger("jistory.index")

_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="jistory-index")
_lock = threading.Lock()
_queued: set[str] = set()


def schedule_embedding_index(import_job_id: str) -> None:
    """Index embeddings after parse returns. Safe to call more than once."""
    with _lock:
        if import_job_id in _queued:
            return
        _queued.add(import_job_id)
    _executor.submit(_run_index_job, import_job_id)


def wait_for_background_jobs(timeout: float = 8.0) -> None:
    """Block until in-flight index jobs finish. Used by tests."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        with _lock:
            if not _queued:
                return
        time.sleep(0.02)


def _run_index_job(import_job_id: str) -> None:
    try:
        _index(import_job_id)
    except Exception:
        logger.exception("Background embedding index crashed")
    finally:
        with _lock:
            _queued.discard(import_job_id)


def _index(import_job_id: str) -> None:
    db = get_session_factory()()
    try:
        job = db.get(ImportJob, import_job_id)
        if job is None:
            return
        job.status = ImportStatus.INDEXING.value
        job.index_error = None
        db.add(job)
        db.commit()

        count = index_import_job(db, import_job_id)

        job = db.get(ImportJob, import_job_id)
        if job is None:
            return
        job.chunks_indexed = count
        job.status = ImportStatus.READY.value
        job.index_error = None
        db.add(job)
        db.commit()
        logger.info("Indexed import job chunks=%s", count)
        _rebuild_graph(db)
    except EmbeddingUnavailableError as exc:
        db.rollback()
        _mark_parsed_with_error(db, import_job_id, exc.message)
        set_embedding_status("unavailable", exc.message)
        _rebuild_graph(db)
    except Exception:
        logger.exception("Embedding index failed")
        db.rollback()
        _mark_parsed_with_error(
            db,
            import_job_id,
            "Keyword search is ready, but semantic indexing failed. Try parsing again.",
        )
        _rebuild_graph(db)
    finally:
        db.close()


def _rebuild_graph(db) -> None:
    try:
        from app.graph.builder import rebuild_conversation_edges

        rebuild_conversation_edges(db)
        db.commit()
    except Exception:
        logger.exception("Memory graph rebuild failed")
        db.rollback()
        try:
            from app.graph.builder import invalidate_graph

            invalidate_graph(db)
            db.commit()
        except Exception:
            logger.exception("Could not invalidate memory graph after rebuild failure")
            db.rollback()


def _mark_parsed_with_error(db, import_job_id: str, message: str) -> None:
    job = db.get(ImportJob, import_job_id)
    if job is None:
        return
    job.status = ImportStatus.PARSED.value
    job.index_error = message
    db.add(job)
    db.commit()
