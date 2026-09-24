"""Turning clinical documents into rows.

Everything in this package runs locally and deterministically. Nothing here may
call an AI model or open a network connection — see the docstring of
app/ingest/pdf.py, and tests/test_pdf_ingest_isolation.py which enforces it.
"""
