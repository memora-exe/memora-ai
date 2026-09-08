"""Backward-compatibility shim — re-exports start_consumer.

Will be deleted in Phase 6.
"""
from app.services.ingestion.consumer import start_consumer

__all__ = ["start_consumer"]
