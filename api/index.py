"""Vercel serverless entry point - imports Flask app from package."""

from bot_app import app

__all__ = ["app"]

# Vercel serves this as the WSGI handler
# All routes defined in bot_app/routes.py

