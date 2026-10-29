from __future__ import annotations

import uuid
from typing import Any

RULE_VERSION = "thresholds-v1"


class Detector:
    def __init__(self, cpu_threshold: float, cpu_samples: int, memory_threshold: float, disk_free_threshold: float, process_memory_delta_bytes: int = 262144000):
        self.cpu_threshold, self.cpu_samples = cpu_threshold, cpu_samples
        self.memory_threshold, self.disk_free_threshold = memory_threshold, disk_free_threshold
        self.process_memory_delta_bytes = process_memory_delta_bytes
        self._cpu_streak = 0
        self._cpu_started_at: str | None = None
        self._active: set[str] = set()
        self._process_baseline: dict[int, int] = {}

    def inspect(self, metrics: dict[str, Any]) -> list[dict[str, Any]]:
        events = []
        if metrics["cpu_percent"] >= self.cpu_threshold:
            if self._cpu_streak == 0:
                self._cpu_started_at = metrics["observed_at"]
            self._cpu_streak += 1
        else:
            self._cpu_streak, self._cpu_started_at = 0, None
            self._active.discard("high_cpu")
        if self._cpu_streak >= self.cpu_samples and "high_cpu" not in self._active:
            events.append(self._event("high_cpu", metrics, metrics["cpu_percent"], self.cpu_threshold, "%", "warning", self._cpu_started_at))
            self._active.add("high_cpu")
        if metrics["memory_percent"] >= self.memory_threshold:
            if "high_memory" not in self._active:
                events.append(self._event("high_memory", metrics, metrics["memory_percent"], self.memory_threshold, "%", "warning"))
                self._active.add("high_memory")
        else:
            self._active.discard("high_memory")
        disk_free = 100 - metrics["disk_percent"]
        if disk_free <= self.disk_free_threshold:
            if "low_disk_space" not in self._active:
                events.append(self._event("low_disk_space", metrics, disk_free, self.disk_free_threshold, "% free", "critical"))
                self._active.add("low_disk_space")
        else:
            self._active.discard("low_disk_space")
        return events

    def inspect_processes(self, processes: list[dict[str, Any]], observed_at: str) -> list[dict[str, Any]]:
        events = []
        current = {p["pid"]: p.get("memory_rss_bytes") for p in processes if isinstance(p.get("pid"), int) and isinstance(p.get("memory_rss_bytes"), int)}
        for pid, memory in current.items():
            old = self._process_baseline.get(pid)
            delta = memory - old if old is not None else 0
            key = f"process_memory:{pid}"
            if delta >= self.process_memory_delta_bytes and key not in self._active:
                record = {"observed_at": observed_at}
                event = self._event("process_memory_increase", record, delta, self.process_memory_delta_bytes, "bytes per sample", "warning")
                event["evidence"].update({"pid": pid, "process_name": next((p.get("name") for p in processes if p.get("pid") == pid), "unknown"), "previous_rss_bytes": old, "current_rss_bytes": memory})
                event["rule_id"] = f"{RULE_VERSION}:process_memory_delta"
                events.append(event)
                self._active.add(key)
            elif delta < self.process_memory_delta_bytes:
                self._active.discard(key)
        self._process_baseline = current
        return events

    @staticmethod
    def _event(kind: str, metrics: dict[str, Any], value: float, threshold: float, unit: str, severity: str, started_at: str | None = None) -> dict[str, Any]:
        return {
            "id": str(uuid.uuid4()), "type": kind, "severity": severity,
            "observed_at": metrics["observed_at"], "started_at": started_at or metrics["observed_at"],
            "value": value, "threshold": threshold, "unit": unit,
            "source": "psutil system snapshot", "rule_id": f"{RULE_VERSION}:{kind}",
            "evidence": {"metric_timestamp": metrics["observed_at"]},
        }
