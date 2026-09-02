"""Index every PDF already placed in the configured knowledge directory."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent_core.runtime.config import load_settings  # noqa: E402
from agent_core.knowledge.rag import KnowledgeService  # noqa: E402
from agent_core.persistence.store import Database  # noqa: E402


def main() -> None:
    settings = load_settings()
    service = KnowledgeService(Database(settings.database_url), settings.knowledge_dir, settings.embedding_model)
    settings.knowledge_dir.mkdir(parents=True, exist_ok=True)
    files = list(settings.knowledge_dir.glob("*.pdf"))
    if not files:
        print(f"Không có PDF trong {settings.knowledge_dir}")
        return
    for path in files:
        document, created = service.upload(path.name, path.read_bytes())
        result = service.index(document.id) if created or document.status != "ready" else document
        print(f"{result.status}: {result.original_name}" + (f" — {result.error}" if result.error else ""))


if __name__ == "__main__":
    main()
