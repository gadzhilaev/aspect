"""Real signal ingestion — fetch → dedupe → cluster → enrich → publish."""

from app.services.ingestion.pipeline import IngestResult, run_ingestion

__all__ = ["run_ingestion", "IngestResult"]
