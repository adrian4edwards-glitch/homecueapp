"""On-disk project store: data/projects/<id>/project.json + media/."""
from __future__ import annotations

import shutil
import threading
import time
from pathlib import Path
from typing import Optional

from .config import settings
from .models import Project


class ProjectStore:
    def __init__(self, root: Optional[Path] = None):
        self.root = Path(root) if root else settings.projects_dir
        self.root.mkdir(parents=True, exist_ok=True)
        self._locks: dict[str, threading.RLock] = {}
        self._guard = threading.Lock()

    def lock(self, pid: str) -> threading.RLock:
        with self._guard:
            return self._locks.setdefault(pid, threading.RLock())

    def dir(self, pid: str) -> Path:
        return self.root / pid

    def media(self, pid: str, *sub: str) -> Path:
        p = self.dir(pid).joinpath("media", *sub)
        p.mkdir(parents=True, exist_ok=True)
        return p

    def abspath(self, pid: str, rel: Optional[str]) -> Optional[Path]:
        return (self.dir(pid) / rel) if rel else None

    def rel(self, pid: str, path: Path) -> str:
        return str(Path(path).resolve().relative_to(self.dir(pid).resolve()))

    def save(self, project: Project) -> Project:
        with self.lock(project.id):
            project.updated = time.time()
            d = self.dir(project.id)
            d.mkdir(parents=True, exist_ok=True)
            tmp = d / "project.json.tmp"
            tmp.write_text(project.model_dump_json(indent=1))
            tmp.replace(d / "project.json")
        return project

    def load(self, pid: str) -> Project:
        f = self.dir(pid) / "project.json"
        if not f.exists():
            raise KeyError(pid)
        with self.lock(pid):
            return Project.model_validate_json(f.read_text())

    def list(self) -> list[dict]:
        out = []
        for f in self.root.glob("*/project.json"):
            try:
                p = Project.model_validate_json(f.read_text())
            except Exception:
                continue
            out.append({"id": p.id, "title": p.bible.title, "logline": p.bible.logline, "genre": p.bible.genre,
                        "medium": p.bible.style.medium, "scenes": len(p.scenes),
                        "shots": sum(len(s.shots) for s in p.scenes), "duration": round(p.duration, 1),
                        "updated": p.updated, "renders": len(p.renders)})
        return sorted(out, key=lambda x: -x["updated"])

    def delete(self, pid: str) -> None:
        shutil.rmtree(self.dir(pid), ignore_errors=True)
