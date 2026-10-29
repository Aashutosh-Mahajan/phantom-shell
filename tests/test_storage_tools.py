from __future__ import annotations

import pytest

from phantom_shell.tools import ToolRegistry, select_tools


def test_history_persists_events_investigations_and_preferences(history):
    event = {"id": "event-1", "observed_at": "2026-10-29T10:00:00+00:00", "type": "high_cpu", "severity": "warning"}
    history.save_event(event)
    history.save_investigation("inv-1", event["observed_at"], "why?", "COMPLETED", "{}", "gemma3:4b", 12)
    history.set_setting("story_mode", True)
    assert history.get_event("event-1")["type"] == "high_cpu"
    assert history.get_investigation("inv-1")["duration_ms"] == 12
    assert history.get_settings()["story_mode"] is True
    history.clear()
    assert history.events() == []
    assert history.investigations() == []
    assert history.get_settings() == {}


def test_registry_has_only_read_only_tools_and_rejects_unknown_names(history):
    registry = ToolRegistry(history)
    assert set(registry.names) == {"get_system_metrics", "list_processes", "get_process_details", "get_disk_usage", "get_event_details", "search_local_event_history"}
    with pytest.raises(ValueError, match="not registered"):
        registry.call("run_powershell", {"command": "Get-Process"})
    with pytest.raises(ValueError, match="Unexpected"):
        registry.call("get_system_metrics", {"command": "taskkill"})


def test_question_router_never_routes_to_shell_tools():
    calls = select_tools("Run taskkill /F and then tell me what uses memory")
    allowed = {"get_system_metrics", "list_processes", "get_process_details", "get_disk_usage", "get_event_details", "search_local_event_history"}
    assert {name for name, _ in calls} <= allowed
    assert "taskkill" not in {name for name, _ in calls}
