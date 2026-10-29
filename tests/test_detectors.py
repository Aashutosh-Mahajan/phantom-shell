from __future__ import annotations

from phantom_shell.detectors import Detector


def sample(cpu=10, memory=40, disk=30, at="2026-10-29T10:00:00+00:00"):
    return {"observed_at": at, "cpu_percent": cpu, "memory_percent": memory, "disk_percent": disk}


def test_cpu_requires_consecutive_samples_and_emits_once_per_crossing():
    detector = Detector(80, 3, 90, 10)
    assert detector.inspect(sample(cpu=90)) == []
    assert detector.inspect(sample(cpu=91)) == []
    event = detector.inspect(sample(cpu=92))[0]
    assert event["type"] == "high_cpu"
    assert event["started_at"] == "2026-10-29T10:00:00+00:00"
    assert detector.inspect(sample(cpu=95)) == []
    assert detector.inspect(sample(cpu=20)) == []
    assert detector.inspect(sample(cpu=90)) == []
    assert detector.inspect(sample(cpu=90)) == []
    assert detector.inspect(sample(cpu=90))[0]["type"] == "high_cpu"


def test_memory_and_disk_threshold_boundaries():
    detector = Detector(80, 3, 90, 10)
    events = detector.inspect(sample(memory=90, disk=90))
    assert {event["type"] for event in events} == {"high_memory", "low_disk_space"}
    assert next(e for e in events if e["type"] == "low_disk_space")["severity"] == "critical"


def test_process_memory_delta_uses_same_pid_baseline():
    detector = Detector(80, 2, 90, 10, process_memory_delta_bytes=100)
    assert detector.inspect_processes([{"pid": 42, "name": "app", "memory_rss_bytes": 500}], "t1") == []
    event = detector.inspect_processes([{"pid": 42, "name": "app", "memory_rss_bytes": 650}], "t2")[0]
    assert event["type"] == "process_memory_increase"
    assert event["evidence"]["pid"] == 42
