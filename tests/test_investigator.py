from __future__ import annotations

import json

from phantom_shell.investigator import Investigator


class FakeRegistry:
    def __init__(self, fail=False):
        self.fail = fail

    def call(self, name, arguments):
        if self.fail:
            raise RuntimeError("fixture collection failure")
        if name == "get_system_metrics":
            return {"observed_at": "2026-10-29T10:00:00+00:00", "cpu_percent": 45.0, "memory_percent": 60.0, "disk_percent": 40.0, "uptime_seconds": 500}
        if name == "list_processes":
            return [{"pid": 55, "name": "editor.exe", "memory_rss_bytes": 500, "cpu_percent": 1.2, "executable": "editor.exe"}]
        raise AssertionError(f"unexpected tool call: {name}")


class FakeOllama:
    def __init__(self, invalid_reference=False):
        self.invalid_reference = invalid_reference
        self.schema = None

    def generate(self, prompt, schema=None):
        self.schema = schema
        packet = json.loads(prompt.split("EVIDENCE PACKET (JSON):\n", 1)[1])
        evidence_id = "not-collected" if self.invalid_reference else packet["observations"][0]["id"]
        return json.dumps({
            "summary": "The editor.exe process may contribute.",
            "hypotheses": [{"claim": "A process may contribute to resource use.", "evidence_ids": [evidence_id], "confidence": "medium"}],
            "recommendations": ["Review the process list."],
            "limitations": [],
        })


class RepairingOllama(FakeOllama):
    def __init__(self):
        super().__init__()
        self.calls = 0

    def generate(self, prompt, schema=None):
        self.calls += 1
        if self.calls == 1:
            return '{"summary": "unfinished'
        return super().generate(prompt, schema)


def test_investigation_separates_measured_facts_and_validates_ids(history):
    ollama = FakeOllama()
    result = Investigator(ollama, FakeRegistry(), history, "gemma3:4b").investigate("What is using memory?")
    assert result["status"] == "COMPLETED"
    assert result["facts"]
    assert result["hypotheses"][0]["evidence_ids"]
    assert "hypothesis" in result["summary"]
    assert ollama.schema["type"] == "object"
    assert history.get_investigation(result["investigation_id"])["status"] == "COMPLETED"


def test_ungrounded_assessment_becomes_inconclusive(history):
    result = Investigator(FakeOllama(invalid_reference=True), FakeRegistry(), history, "gemma3:4b").investigate("What is using memory?")
    assert result["status"] == "INCONCLUSIVE"
    assert result["hypotheses"] == []
    assert any("rejected" in item for item in result["limitations"])


def test_malformed_json_gets_one_bounded_repair_attempt(history):
    ollama = RepairingOllama()
    result = Investigator(ollama, FakeRegistry(), history, "gemma3:4b").investigate("What is using memory?")
    assert result["status"] == "COMPLETED"
    assert ollama.calls == 2


def test_collection_failure_does_not_send_empty_evidence_to_model(history):
    ollama = FakeOllama()
    result = Investigator(ollama, FakeRegistry(fail=True), history, "gemma3:4b").investigate("What is the CPU doing?")
    assert result["status"] == "INCONCLUSIVE"
    assert ollama.schema is None
    assert result["evidence"]["collection_errors"]
