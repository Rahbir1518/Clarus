"""No AI model, and no network, touches an uploaded PDF.

The previous backend sent every uploaded document to Google Gemini whenever an
API key was configured. These tests make the replacement's guarantee
mechanical, so it survives the next person who thinks "an LLM would parse this
better":

  1. The ingest package and the intake route import only from an allowlist. An
     allowlist rather than a list of banned AI SDKs, because the next SDK is
     one nobody has banned yet — and an HTTP client is all it takes.
  2. A document parses, and the intake route runs end to end, with every
     socket connection refused.
  3. No AI SDK is a declared dependency of the backend.

If one of these fails, the fix is not to widen the allowlist. It is to talk to
whoever owns patient data first.
"""
import ast
import socket
import tomllib
from pathlib import Path

import pytest

from app.ingest.pdf import parse_pdf
from tests.pdf_fixtures import LAB_REPORT, make_pdf

BACKEND = Path(__file__).resolve().parent.parent

# Every file that holds document content before it reaches the database.
GUARDED_FILES = [
    *sorted((BACKEND / "app" / "ingest").glob("*.py")),
    BACKEND / "app" / "api" / "routes" / "documents.py",
]

ALLOWED_IMPORTS = {
    "__future__",
    "dataclasses",
    "datetime",
    "io",
    "logging",
    "re",
    "typing",
    "pypdf",
    "fastapi",
    "app.api.deps",
    "app.ingest",
}

AI_PACKAGES = (
    "openai", "anthropic", "google-genai", "google-generativeai", "langchain",
    "llama", "mistral", "cohere", "groq", "together", "replicate", "huggingface",
    "transformers", "litellm", "ollama", "elevenlabs", "vertexai",
)


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            found.add(node.module or "")
        elif isinstance(node, ast.Call) and getattr(node.func, "id", "") == "__import__":
            found.add("<dynamic __import__>")
    return found


def _allowed(module: str) -> bool:
    return any(module == ok or module.startswith(ok + ".") for ok in ALLOWED_IMPORTS)


@pytest.mark.parametrize("path", GUARDED_FILES, ids=lambda p: p.name)
def test_pdf_code_imports_nothing_that_could_send_a_document_away(path):
    assert path.exists(), f"{path} moved; update GUARDED_FILES"
    offending = sorted(m for m in _imports(path) if not _allowed(m))
    assert not offending, (
        f"{path.relative_to(BACKEND)} imports {offending}. PDF content must not "
        "reach an AI model or the network — see this test's docstring."
    )


@pytest.fixture
def no_network(monkeypatch: pytest.MonkeyPatch):
    def _refuse(*_args, **_kwargs):
        raise AssertionError("PDF ingestion attempted a network connection")

    monkeypatch.setattr(socket.socket, "connect", _refuse)
    monkeypatch.setattr(socket.socket, "connect_ex", _refuse)
    monkeypatch.setattr(socket, "create_connection", _refuse)
    monkeypatch.setattr(socket, "getaddrinfo", _refuse)


def test_parsing_works_with_the_network_switched_off(no_network):
    doc = parse_pdf(make_pdf(LAB_REPORT))
    assert doc.patient_info["name"] == "Rahim Uddin"


def test_the_intake_route_works_with_the_network_switched_off(
    client, auth_header, no_network
):
    # TestClient runs in-process, so any socket use here came from the route.
    response = client.post(
        "/api/pdf/intake",
        files={"file": ("r.pdf", make_pdf(LAB_REPORT), "application/pdf")},
        headers=auth_header("user_2alice"),
    )
    assert response.status_code == 201, response.text


def test_no_ai_sdk_is_a_backend_dependency():
    project = tomllib.loads((BACKEND / "pyproject.toml").read_text(encoding="utf-8"))
    declared = [
        dep.lower()
        for group in [project["project"]["dependencies"],
                      *project["project"].get("optional-dependencies", {}).values()]
        for dep in group
    ]
    hits = [d for d in declared for ai in AI_PACKAGES if d.startswith(ai)]
    assert not hits, f"AI SDK declared as a dependency: {hits}"
