from __future__ import annotations

import json

import pytest

from phantom_shell.evidence import EvidencePacket, validate_assessment


def test_packet_caps_size_and_preserves_only_bounded_observations():
    packet = EvidencePacket.create("check", "now")
    for _ in range(30):
        packet.add_observation("process", {"value": "x" * 2000}, "fixture")
    result = packet.bounded_dict()
    assert len(json.dumps(result).encode()) <= 24_000


def test_model_hypotheses_must_reference_real_evidence():
    raw = json.dumps({"summary": "x", "hypotheses": [{"claim": "possible", "evidence_ids": ["ev-real"], "confidence": "medium"}], "recommendations": [], "limitations": []})
    assert validate_assessment(raw, {"ev-real"})["hypotheses"][0]["evidence_ids"] == ["ev-real"]
    with pytest.raises(ValueError, match="not collected"):
        validate_assessment(raw, {"ev-other"})


def test_destructive_recommendations_are_filtered():
    raw = json.dumps({"summary": "x", "hypotheses": [], "recommendations": ["Review the largest process.", "Terminate the process."], "limitations": []})
    parsed = validate_assessment(raw, set())
    assert parsed["recommendations"] == ["Review the largest process."]
