from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Callable

from .storage import History
from .telemetry import collect_metrics, disk_usage, get_process_details, list_processes

MAX_TOOL_CALLS = 3
MAX_TOOL_OUTPUT = 12_000


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    run: Callable[[dict[str, Any]], Any]


class ToolRegistry:
    """The complete read-only tool boundary; no shell or mutation capability exists."""
    def __init__(self, history: History):
        self.history = history
        self._tools = {
            "get_system_metrics": Tool("get_system_metrics", "Collect current CPU, memory, disk and uptime metrics", self._metrics),
            "list_processes": Tool("list_processes", "List processes by memory or CPU use", self._processes),
            "get_process_details": Tool("get_process_details", "Read safe metadata for one process ID", self._process),
            "get_disk_usage": Tool("get_disk_usage", "Read usage for a filesystem path", self._disk),
            "get_event_details": Tool("get_event_details", "Retrieve one stored anomaly by event ID", self._event),
            "search_local_event_history": Tool("search_local_event_history", "Search bounded local anomaly history", self._search),
        }

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(self._tools)

    def call(self, name: str, arguments: dict[str, Any]) -> Any:
        tool = self._tools.get(name)
        if tool is None:
            raise ValueError(f"Tool is not registered: {name}")
        if not isinstance(arguments, dict):
            raise ValueError("Tool arguments must be an object")
        result = tool.run(arguments)
        # enforce output cap before putting tool data into the prompt
        import json
        encoded = json.dumps(result, ensure_ascii=True)
        if len(encoded.encode("utf-8")) > MAX_TOOL_OUTPUT:
            raise ValueError("Tool result exceeded the configured output limit")
        return result

    @staticmethod
    def _check_keys(args: dict[str, Any], allowed: set[str]) -> None:
        if set(args) - allowed:
            raise ValueError("Unexpected tool argument")

    def _metrics(self, args: dict[str, Any]) -> Any:
        self._check_keys(args, set())
        return collect_metrics()

    def _processes(self, args: dict[str, Any]) -> Any:
        self._check_keys(args, {"limit", "sort"})
        limit, sort = args.get("limit", 15), args.get("sort", "memory")
        if type(limit) is not int or not 1 <= limit <= 30 or sort not in {"memory", "cpu"}:
            raise ValueError("list_processes expects limit 1..30 and sort 'memory' or 'cpu'")
        return list_processes(limit, sort)

    def _process(self, args: dict[str, Any]) -> Any:
        self._check_keys(args, {"pid"})
        pid = args.get("pid")
        if type(pid) is not int or pid < 1:
            raise ValueError("pid must be a positive integer")
        return get_process_details(pid)

    def _disk(self, args: dict[str, Any]) -> Any:
        self._check_keys(args, {"path"})
        from .telemetry import system_root
        path = args.get("path", system_root())
        if not isinstance(path, str) or path != system_root():
            raise ValueError("Only the configured local system drive root can be inspected")
        return disk_usage(path)

    def _event(self, args: dict[str, Any]) -> Any:
        self._check_keys(args, {"event_id"})
        event_id = args.get("event_id")
        if not isinstance(event_id, str) or len(event_id) > 64:
            raise ValueError("event_id must be a valid ID")
        event = self.history.get_event(event_id)
        if event is None:
            raise ValueError("No event exists with that ID")
        return event

    def _search(self, args: dict[str, Any]) -> Any:
        self._check_keys(args, {"query", "limit"})
        query, limit = args.get("query", ""), args.get("limit", 10)
        if not isinstance(query, str) or len(query) > 100 or type(limit) is not int or not 1 <= limit <= 30:
            raise ValueError("query must be <= 100 characters and limit 1..30")
        return self.history.search_events(query, limit)


def select_tools(question: str) -> list[tuple[str, dict[str, Any]]]:
    """Deterministic routing means user/model text never chooses executable code."""
    q = question.casefold()
    calls: list[tuple[str, dict[str, Any]]] = [("get_system_metrics", {})]
    event_match = re.search(r"\b([0-9a-f]{8}-[0-9a-f-]{27,36})\b", q)
    pid_match = re.search(r"\bpid\s*[:#]?\s*(\d{1,10})\b", q)
    if event_match:
        calls.append(("get_event_details", {"event_id": event_match.group(1)}))
    elif pid_match:
        calls.append(("get_process_details", {"pid": int(pid_match.group(1))}))
    if any(term in q for term in ("process", "memory", "ram", "cpu", "consum", "slow", "performance")):
        calls.append(("list_processes", {"limit": 15, "sort": "memory" if any(t in q for t in ("memory", "ram")) else "cpu"}))
    if any(term in q for term in ("disk", "drive", "space", "storage")):
        from .telemetry import system_root
        calls.append(("get_disk_usage", {"path": system_root()}))
    if any(term in q for term in ("event", "anomaly", "history", "alert", "incident", "error")):
        calls.append(("search_local_event_history", {"query": "", "limit": 10}))
    return calls[:MAX_TOOL_CALLS]
