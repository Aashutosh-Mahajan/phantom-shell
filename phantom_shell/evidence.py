from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from typing import Any

MAX_PACKET_BYTES = 24_000


@dataclass
class EvidencePacket:
    investigation_id: str
    question: str
    created_at: str
    observations: list[dict[str, Any]] = field(default_factory=list)
    anomalies: list[dict[str, Any]] = field(default_factory=list)
    errors: list[dict[str, str]] = field(default_factory=list)
    tools_run: list[str] = field(default_factory=list)

    @classmethod
    def create(cls, question: str, created_at: str) -> "EvidencePacket":
        return cls(str(uuid.uuid4()), question[:1000], created_at)

    def add_observation(self, kind: str, value: Any, source: str) -> str:
        evidence_id = f"ev-{uuid.uuid4().hex[:12]}"
        self.observations.append({"id": evidence_id, "kind": kind, "source": source, "value": value})
        return evidence_id

    def add_anomaly(self, value: dict[str, Any]) -> str:
        evidence_id = f"ev-{uuid.uuid4().hex[:12]}"
        evidence = value.get("evidence", {}) if isinstance(value.get("evidence"), dict) else {}
        safe_evidence = {key: evidence[key] for key in ("metric_timestamp", "pid", "process_name", "previous_rss_bytes", "current_rss_bytes") if key in evidence}
        self.anomalies.append({
            "id": evidence_id, "event_id": str(value.get("id", ""))[:64], "type": str(value.get("type", "unknown"))[:80],
            "severity": str(value.get("severity", "unknown"))[:20], "started_at": str(value.get("started_at", ""))[:64],
            "observed_at": str(value.get("observed_at", ""))[:64], "value": value.get("value"),
            "threshold": value.get("threshold"), "unit": str(value.get("unit", ""))[:32],
            "rule_id": str(value.get("rule_id", ""))[:100], "evidence": safe_evidence,
        })
        return evidence_id

    def allowed_ids(self, packet: dict[str, Any] | None = None) -> set[str]:
        source = packet or {"observations": self.observations, "anomalies": self.anomalies}
        return {item["id"] for item in source.get("observations", [])} | {item["id"] for item in source.get("anomalies", [])}

    def bounded_dict(self) -> dict[str, Any]:
        packet = {
            "investigation_id": self.investigation_id,
            "question": self.question,
            "created_at": self.created_at,
            "observations": self.observations,
            "anomalies": self.anomalies,
            "collection_errors": self.errors,
            "tools_run": self.tools_run,
        }
        encoded = json.dumps(packet, ensure_ascii=True, separators=(",", ":"))
        if len(encoded.encode("utf-8")) <= MAX_PACKET_BYTES:
            return packet
        # Keep recent/high relevance evidence while respecting a hard prompt bound.
        packet["observations"] = packet["observations"][-12:]
        packet["anomalies"] = packet["anomalies"][-10:]
        packet["collection_errors"] = packet["collection_errors"][-8:]
        packet["question"] = packet["question"][:400]
        while len(json.dumps(packet, ensure_ascii=True).encode("utf-8")) > MAX_PACKET_BYTES and packet["observations"]:
            packet["observations"].pop(0)
        while len(json.dumps(packet, ensure_ascii=True).encode("utf-8")) > MAX_PACKET_BYTES and packet["anomalies"]:
            packet["anomalies"].pop(0)
        if len(json.dumps(packet, ensure_ascii=True).encode("utf-8")) > MAX_PACKET_BYTES:
            packet["collection_errors"] = [{"tool": "packet", "error": "Evidence was truncated to enforce the prompt size limit."}]
        return packet


def validate_assessment(raw: str, allowed_ids: set[str]) -> dict[str, Any]:
    """Parse and validate the model contract; never accept ungrounded references."""
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("Model response did not contain a JSON assessment")
    data = json.loads(raw[start:end + 1])
    if not isinstance(data, dict):
        raise ValueError("Assessment must be a JSON object")
    hypotheses = data.get("hypotheses", [])
    recommendations = data.get("recommendations", [])
    if not isinstance(hypotheses, list) or not isinstance(recommendations, list):
        raise ValueError("Assessment fields have invalid types")
    clean_hypotheses = []
    invalid_refs: list[str] = []
    for item in hypotheses[:6]:
        if not isinstance(item, dict) or not isinstance(item.get("claim"), str):
            continue
        refs = item.get("evidence_ids", [])
        if not isinstance(refs, list):
            refs = []
        valid = [ref for ref in refs if isinstance(ref, str) and ref in allowed_ids]
        invalid_refs.extend(str(ref) for ref in refs if ref not in valid)
        if valid:
            clean_hypotheses.append({"claim": item["claim"][:600], "evidence_ids": valid, "confidence": item.get("confidence", "uncertain") if item.get("confidence") in {"low", "medium", "high", "uncertain"} else "uncertain"})
    clean_recommendations = [str(item)[:400] for item in recommendations[:5] if isinstance(item, str)]
    if invalid_refs:
        raise ValueError("Assessment cited evidence IDs that were not collected")
    if hypotheses and not clean_hypotheses:
        raise ValueError("Assessment contained no hypotheses grounded in collected evidence")
    unsafe_terms = ("taskkill", "kill", "terminate", "delete", "remove", "format", "stop", "close", "disable", "uninstall", "restart", "modify", "change", "edit", "write", "install", "reset", "end process", "powershell", "cmd.exe", "registry", "firewall", "security settings")
    clean_recommendations = [item for item in clean_recommendations if not any(term in item.casefold() for term in unsafe_terms)]
    return {"summary": str(data.get("summary", "Assessment returned no summary."))[:800], "hypotheses": clean_hypotheses, "recommendations": clean_recommendations, "limitations": [str(item)[:300] for item in data.get("limitations", [])[:6] if isinstance(item, str)]}
