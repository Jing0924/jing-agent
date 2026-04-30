"""ASGI entrypoint; run from backend/: uvicorn main:app --reload"""

from memoir_rag.api_app import app

__all__ = ["app"]
