"""Local-only conversation persistence; no provider configuration or raw recordings."""
import copy
import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path


class ConversationStore:
    def __init__(self, root: Path):
        self.directory = Path(root) / "conversations"
        self.directory.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._requests = {}
        self._items = {}
        for path in self.directory.glob("*.json"):
            try:
                item = json.loads(path.read_text(encoding="utf-8"))
                if item.get("id") == path.stem and isinstance(item.get("messages"), list):
                    self._items[path.stem] = item
            except (OSError, ValueError, AttributeError):
                continue

    def _write(self, item):
        target = self.directory / (item["id"] + ".json")
        temporary = target.with_suffix(".tmp")
        temporary.write_text(json.dumps(item, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(target)
        self._items[item["id"]] = item

    def create(self, job_id=None, title=None):
        now = datetime.now(timezone.utc).isoformat()
        item = {"id": uuid.uuid4().hex, "title": (title or "").strip()[:100],
                "job_id": job_id, "messages": [], "created_at": now, "updated_at": now}
        with self._lock:
            self._write(item)
            return copy.deepcopy(item)

    def list(self):
        with self._lock:
            return copy.deepcopy(sorted(self._items.values(), key=lambda item: item["updated_at"], reverse=True))

    def get(self, conversation_id):
        with self._lock:
            return copy.deepcopy(self._items[conversation_id])

    def request_lock(self, conversation_id):
        with self._lock:
            if conversation_id not in self._items:
                raise KeyError(conversation_id)
            return self._requests.setdefault(conversation_id, threading.Lock())

    def append_exchange(self, conversation_id, question, answer, include_summary=False):
        with self._lock:
            item = self.get(conversation_id)
            now = datetime.now(timezone.utc).isoformat()
            item["messages"].extend([
                {"role": "user", "content": question, "created_at": now, "include_summary": bool(include_summary)},
                {"role": "assistant", "content": answer, "created_at": now},
            ])
            if not item["title"]:
                item["title"] = question.strip()[:60]
            item["updated_at"] = now
            self._write(item)
            return copy.deepcopy(item)
