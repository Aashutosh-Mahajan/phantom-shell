from __future__ import annotations

import json
from typing import Any


def _console(plain: bool = False):
    try:
        from rich.console import Console
        return Console(no_color=plain, highlight=False)
    except ImportError:
        return None


def banner(plain: bool = False) -> None:
    console = _console(plain)
    title = "PHANTOM SHELL  /  GHOST IN THE MACHINE"
    if console:
        from rich.panel import Panel
        console.print(Panel.fit(title, border_style="magenta" if not plain else "white", subtitle="LOCAL SYSTEM INVESTIGATOR"))
    else:
        print(title)


def show_metrics(metrics: dict[str, Any], model_status: str | None = None, plain: bool = False) -> None:
    console = _console(plain)
    if console:
        from rich.text import Text
        from rich.table import Table
        table = Table(title="OBSERVATION | measured locally", border_style="magenta" if not plain else "white")
        table.add_column("Signal", style="cyan" if not plain else None)
        table.add_column("Reading", justify="right")
        table.add_row("CPU", f"{metrics['cpu_percent']:.1f}%")
        table.add_row("Memory", f"{metrics['memory_percent']:.1f}%  ({metrics['memory_used_bytes']:,} / {metrics['memory_total_bytes']:,} bytes)")
        table.add_row("System disk", f"{metrics['disk_percent']:.1f}% used  ({metrics['disk_free_bytes']:,} bytes free)")
        table.add_row("Uptime", _duration(metrics["uptime_seconds"]))
        table.add_row("Observed at", metrics["observed_at"])
        console.print(table)
        if model_status:
            status = Text("MODEL ", style="bold magenta" if not plain else None)
            status.append(_clean(model_status))
            console.print(status)
    else:
        print(json.dumps(metrics, indent=2))
        if model_status:
            print("MODEL " + model_status)


def show_event(event: dict[str, Any], plain: bool = False) -> None:
    console = _console(plain)
    label = f"ANOMALY | {event.get('severity', 'unknown').upper()} | {event.get('type', 'event')}"
    body = "\n".join((f"Event ID: {event.get('id')}", f"Observed: {event.get('observed_at')}", f"Started: {event.get('started_at')}", f"Value: {event.get('value')} {event.get('unit')}", f"Threshold: {event.get('threshold')} {event.get('unit')}", f"Rule: {event.get('rule_id')}", "Evidence: " + json.dumps(event.get("evidence", {}), ensure_ascii=True)))
    if console:
        from rich.panel import Panel
        from rich.text import Text
        console.print(Panel(Text(body), title=Text(label), border_style="red" if event.get("severity") == "critical" else "yellow"))
    else:
        print(label + "\n" + body)


def show_investigation(result: dict[str, Any], plain: bool = False) -> None:
    console = _console(plain)
    if not console:
        print(json.dumps(result, indent=2, ensure_ascii=True))
        return
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text
    status = result["status"]
    console.print(Panel(Text(result.get("summary", "")), title=f"{status} | investigation {result['investigation_id'][:8]}", border_style="green" if status == "COMPLETED" else "yellow"))
    facts = Table(title="OBSERVED FACTS", show_header=True)
    facts.add_column("Measured observation")
    facts.add_column("Evidence IDs")
    for item in result.get("facts", []):
        facts.add_row(Text(item["claim"]), Text(", ".join(item["evidence_ids"])))
    if result.get("facts"):
        console.print(facts)
    hypotheses = Table(title="MODEL HYPOTHESES | not confirmed facts", show_header=True)
    hypotheses.add_column("Hypothesis")
    hypotheses.add_column("Model confidence (not calibrated)")
    hypotheses.add_column("Evidence IDs")
    for item in result.get("hypotheses", []):
        hypotheses.add_row(Text(item["claim"]), Text(item["confidence"]), Text(", ".join(item["evidence_ids"])))
    if result.get("hypotheses"):
        console.print(hypotheses)
    if result.get("recommendations"):
        console.print(Panel(Text("\n".join(f"- {item}" for item in result["recommendations"])), title="READ-ONLY NEXT STEPS"))
    if result.get("limitations"):
        console.print(Panel(Text("\n".join(f"- {item}" for item in result["limitations"])), title="LIMITATIONS", border_style="yellow"))
    evidence = result.get("evidence", {})
    if evidence.get("collection_errors"):
        console.print(Panel(Text(json.dumps(evidence["collection_errors"], indent=2)), title="COLLECTION ERRORS", border_style="red"))
    from rich.text import Text
    console.print(Text(f"Tools: {', '.join(evidence.get('tools_run', [])) or 'none'} | {result.get('duration_ms', 0)} ms | local model {_clean(result.get('model', ''))}", style="dim"))
    if result.get("fictional_narration"):
        console.print(Panel(Text(result["fictional_narration"]), title="FICTION | STORY MODE", border_style="magenta"))


def show_records(records: list[dict[str, Any]], kind: str, plain: bool = False) -> None:
    console = _console(plain)
    if not console:
        print(json.dumps(records, indent=2, ensure_ascii=True))
        return
    from rich.table import Table
    from rich.text import Text
    table = Table(title=kind.upper(), border_style="magenta" if not plain else "white")
    if kind == "events":
        for col in ("observed_at", "severity", "type", "value", "threshold", "id"):
            table.add_column(col)
        for row in records:
            table.add_row(*(Text(_clean(row.get(k, ""))[:80]) for k in ("observed_at", "severity", "type", "value", "threshold", "id")))
    elif kind == "investigations":
        for col in ("observed_at", "status", "question", "id"):
            table.add_column(col)
        for row in records:
            table.add_row(*(Text(_clean(row.get(k, ""))[:90]) for k in ("observed_at", "status", "question", "id")))
    else:
        for col in ("pid", "name", "cpu_percent", "memory_rss_bytes", "executable"):
            table.add_column(col)
        for row in records:
            table.add_row(*(Text(_clean(row.get(k, ""))[:100]) for k in ("pid", "name", "cpu_percent", "memory_rss_bytes", "executable")))
    console.print(table)


def _duration(seconds: int) -> str:
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, sec = divmod(rem, 60)
    return f"{days}d {hours:02}:{minutes:02}:{sec:02}"


def _clean(value: Any) -> str:
    return "".join(char for char in str(value) if char >= " " and char != "\x7f")
