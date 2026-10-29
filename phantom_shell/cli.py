from __future__ import annotations

import argparse
import json
import logging
from logging.handlers import RotatingFileHandler
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any

from .config import Config
from .detectors import Detector
from .investigator import Investigator, tell_story
from .ollama import Ollama
from .storage import History
from .telemetry import collect_metrics, list_processes
from .terminal import banner, show_event, show_investigation, show_metrics, show_records
from .tools import ToolRegistry


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="phantom", description="Local-first, evidence-grounded system investigator")
    parser.add_argument("--config", help="Path to TOML configuration")
    parser.add_argument("--plain", action="store_true", help="Disable color and atmospheric presentation")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("doctor", help="Check local Ollama and whether the configured model tag is installed")
    sub.add_parser("status", help="Show a read-only system snapshot")
    procs = sub.add_parser("processes", help="Show read-only process metadata")
    procs.add_argument("--limit", type=int, default=15)
    sub.add_parser("scan", help="Collect a snapshot and evaluate anomaly rules once")
    sub.add_parser("demo-fixture", help="Show a clearly labeled synthetic anomaly scenario without saving it")
    sub.add_parser("watch", aliases=["monitor"], help="Continuously monitor system metrics until Ctrl+C")
    ask = sub.add_parser("ask", aliases=["investigate"], help="Investigate a question using local evidence and Gemma")
    ask.add_argument("question", nargs="+", help="Question about current system state or local events")
    for command in ("events", "history"):
        item = sub.add_parser(command, help="List recent local anomaly events")
        item.add_argument("--limit", type=int, default=20)
    event = sub.add_parser("event", help="Inspect one stored event by ID")
    event.add_argument("event_id")
    investigations = sub.add_parser("investigations", help="List recent saved investigations")
    investigations.add_argument("--limit", type=int, default=20)
    detail = sub.add_parser("investigation", help="Inspect a saved investigation by ID")
    detail.add_argument("investigation_id")
    story = sub.add_parser("story", help="Enable or disable Story Mode, or narrate one stored event")
    story.add_argument("action", choices=("on", "off", "event"))
    story.add_argument("event_id", nargs="?")
    config = sub.add_parser("config", help="Show effective configuration or write a sample file")
    config.add_argument("action", nargs="?", choices=("show", "init"), default="show")
    sub.add_parser("clear-history", help="Delete local events, investigations, and saved preferences")
    return parser


def main() -> None:
    args = make_parser().parse_args()
    plain = args.plain
    config_path = Path(args.config).expanduser() if args.config else None
    try:
        config = Config.load(config_path)
    except (ValueError, OSError, TypeError) as exc:
        print(f"Invalid configuration: {exc}", file=sys.stderr)
        raise SystemExit(2)
    plain = plain or config.plain_mode
    _configure_logging(config)
    ollama = Ollama(config.ollama_url, config.model, config.timeout_seconds)
    history: History | None = None
    try:
        try:
            history = History(config.database)
        except (sqlite3.Error, OSError) as exc:
            logging.getLogger("phantom_shell").warning("history unavailable (%s)", type(exc).__name__)
            print(f"LOCAL HISTORY UNAVAILABLE | monitoring remains available; this session will not persist data ({str(exc)[:200]})", file=sys.stderr)
            history = History(":memory:")
        history.prune(config.history_retention_days)
        command = args.command or "watch"
        if command == "doctor":
            banner(plain)
            ready, message = ollama.status()
            print(("LOCAL MODEL TAG FOUND | " if ready else "OFFLINE | ") + message)
            print(f"NO CLOUD LLM | configured endpoint {config.ollama_url} | model {config.model}")
            raise SystemExit(0 if ready else 1)
        elif command == "status":
            banner(plain)
            ready, message = ollama.status()
            show_metrics(collect_metrics(), ("OLLAMA ONLINE | " if ready else "OFFLINE | ") + message, plain)
        elif command == "processes":
            if not 1 <= args.limit <= 100:
                raise ValueError("--limit must be between 1 and 100")
            show_records(list_processes(args.limit, "memory"), "processes", plain)
        elif command == "scan":
            detector = _detector(config)
            metrics = collect_metrics()
            processes = list_processes(30)
            events = detector.inspect(metrics) + detector.inspect_processes(processes, metrics["observed_at"])
            show_metrics(metrics, plain=plain)
            for event_data in events:
                _save_event(history, event_data, metrics, processes)
                show_event(event_data, plain)
            if not events:
                print("OBSERVING | no configured thresholds crossed in this snapshot")
        elif command == "demo-fixture":
            print("TEST SCENARIO | synthetic values only | no live finding is created or saved")
            detector = _detector(config)
            event_data = []
            for sample in range(config.cpu_consecutive_samples):
                metrics = {"observed_at": f"FIXTURE-SAMPLE-{sample + 1}", "cpu_percent": 97.0, "memory_percent": 92.0, "disk_percent": 95.0}
                event_data.extend(detector.inspect(metrics))
            for item in event_data:
                show_event(item, plain)
            if not event_data:
                print("The configured thresholds did not trigger this illustrative fixture.")
        elif command in {"watch", "monitor"}:
            detector = _detector(config)
            banner(plain)
            ready, message = ollama.status()
            print(("LOCAL MODEL TAG FOUND | " if ready else "OFFLINE | ") + message)
            try:
                show_metrics(collect_metrics(), plain=plain)
            except Exception as exc:
                print(f"COLLECTION ERROR | initial metrics unavailable ({type(exc).__name__})", file=sys.stderr)
            print(f"OBSERVING | every {config.poll_seconds}s | Ctrl+C to leave")
            try:
                while True:
                    try:
                        metrics = collect_metrics()
                        processes = list_processes(30)
                    except Exception as exc:
                        logging.getLogger("phantom_shell").warning("metric collection skipped (%s)", type(exc).__name__)
                        print(f"COLLECTION ERROR | sample skipped: {str(exc)[:200]}", file=sys.stderr)
                        time.sleep(config.poll_seconds)
                        continue
                    print(f"{metrics['observed_at']}  CPU {metrics['cpu_percent']:.1f}%  MEM {metrics['memory_percent']:.1f}%  DISK {metrics['disk_percent']:.1f}%")
                    events = detector.inspect(metrics) + detector.inspect_processes(processes, metrics["observed_at"])
                    for event_data in events:
                        _save_event(history, event_data, metrics, processes)
                        show_event(event_data, plain)
                    time.sleep(config.poll_seconds)
            except KeyboardInterrupt:
                print("OBSERVATION ENDED | local history saved")
        elif command in {"ask", "investigate"}:
            question = " ".join(args.question).strip()
            if not question or len(question) > 1000:
                raise ValueError("Question must contain 1 to 1000 characters")
            registry = ToolRegistry(history)
            investigator = Investigator(ollama, registry, history, config.model, config.timeout_seconds)
            result = investigator.investigate(question)
            show_investigation(result, plain)
            story_enabled = history.get_settings().get("story_mode", config.story_mode)
            if not plain and story_enabled:
                recent_events = history.events(1)
                if recent_events:
                    ready, message = ollama.status()
                    if ready:
                        print("FICTION | STORY MODE | This narration is fictional and separate from findings.")
                        print(tell_story(ollama, recent_events[0], config.timeout_seconds))
                    else:
                        print("STORY MODE OFFLINE | " + message)
        elif command in {"events", "history"}:
            if not 1 <= args.limit <= 100:
                raise ValueError("--limit must be between 1 and 100")
            show_records(history.events(args.limit), "events", plain)
        elif command == "event":
            found = history.get_event(args.event_id)
            if not found:
                raise ValueError(f"Event not found: {args.event_id}")
            show_event(found, plain)
        elif command == "investigations":
            if not 1 <= args.limit <= 100:
                raise ValueError("--limit must be between 1 and 100")
            show_records(history.investigations(args.limit), "investigations", plain)
        elif command == "investigation":
            found = history.get_investigation(args.investigation_id)
            if not found:
                raise ValueError(f"Investigation not found: {args.investigation_id}")
            try:
                show_investigation(json.loads(found["answer"]), plain)
            except (json.JSONDecodeError, TypeError):
                print(found["answer"])
        elif command == "story":
            if args.action in {"on", "off"}:
                if args.action == "on" and plain:
                    raise ValueError("Story Mode is disabled while plain mode is active")
                history.set_setting("story_mode", args.action == "on")
                print(f"Story Mode {'enabled' if args.action == 'on' else 'disabled'}. Narration is always labeled fiction.")
            else:
                if plain:
                    raise ValueError("Story Mode is disabled while plain mode is active")
                if not args.event_id:
                    raise ValueError("Use: phantom story event <event-id>")
                event_data = history.get_event(args.event_id)
                if not event_data:
                    raise ValueError(f"Event not found: {args.event_id}")
                ready, message = ollama.status()
                if not ready:
                    raise RuntimeError(message)
                print("FICTION | STORY MODE | This is invented narration, not a diagnostic finding.")
                print(tell_story(ollama, event_data, config.timeout_seconds))
        elif command == "config":
            if args.action == "init":
                path = config_path or Path.home() / ".phantom-shell" / "config.toml"
                path.parent.mkdir(parents=True, exist_ok=True)
                if path.exists():
                    raise ValueError(f"Refusing to overwrite existing configuration: {path}")
                path.write_text(_sample_config(config), encoding="utf-8")
                print(f"Sample configuration created at {path}")
            else:
                print(json.dumps({key: str(value) if isinstance(value, Path) else value for key, value in config.__dict__.items()}, indent=2))
                print("Saved preferences: " + json.dumps(history.get_settings()))
        elif command == "clear-history":
            history.clear()
            print("Local history and saved preferences cleared.")
    except (RuntimeError, ValueError, OSError) as exc:
        print(f"PHANTOM SHELL | {exc}", file=sys.stderr)
        raise SystemExit(1)
    finally:
        if history is not None:
            history.close()


def _detector(config: Config) -> Detector:
    return Detector(config.cpu_threshold, config.cpu_consecutive_samples, config.memory_threshold, config.disk_free_threshold, config.process_memory_delta_bytes)


def _configure_logging(config: Config) -> None:
    level = getattr(logging, config.log_level)
    try:
        config.database.parent.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(config.database.parent / "phantom-shell.log", maxBytes=1_000_000, backupCount=2, encoding="utf-8")
        logging.basicConfig(level=level, handlers=[handler], format="%(asctime)s %(levelname)s %(name)s %(message)s")
    except OSError:
        logging.basicConfig(level=level, format="%(levelname)s %(name)s %(message)s")
        logging.getLogger("phantom_shell").warning("local log file unavailable; using standard error")
    logging.getLogger("phantom_shell").info("PHANTOM SHELL started; inference endpoint is loopback-only")


def _save_event(history: History, event: dict[str, Any], metrics: dict[str, Any], processes: list[dict[str, Any]]) -> None:
    event["evidence"].update({"metric_sample": metrics, "process_snapshot": processes[:10]})
    try:
        history.save_event(event)
    except sqlite3.Error as exc:
        print(f"HISTORY WRITE ERROR | event was observed but not saved ({str(exc)[:200]})", file=sys.stderr)


def _sample_config(config: Config) -> str:
    return f'''[phantom]
ollama_url = "{config.ollama_url}"
model = "{config.model}"
poll_seconds = {config.poll_seconds}
cpu_threshold = {config.cpu_threshold}
cpu_consecutive_samples = {config.cpu_consecutive_samples}
memory_threshold = {config.memory_threshold}
disk_free_threshold = {config.disk_free_threshold}
process_memory_delta_bytes = {config.process_memory_delta_bytes}
history_retention_days = {config.history_retention_days}
log_level = "WARNING"
story_mode = false
plain_mode = false
timeout_seconds = {config.timeout_seconds}
'''


if __name__ == "__main__":
    main()
