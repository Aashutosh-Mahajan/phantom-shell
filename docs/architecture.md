# Architecture and safety boundaries

```text
CLI / Rich terminal
        |
        +-- Config validation (loopback Ollama URL only)
        +-- Telemetry (psutil; read-only; bounded process fields)
        +-- Rule detectors (CPU streak, memory, disk, process RSS delta)
        +-- SQLite history (events, investigations, preferences, retention)
        +-- Investigator (Python deterministic router; max 3 tool calls)
                |
                +-- ToolRegistry (fixed names, strict args, output cap)
                +-- EvidencePacket (IDs, error list, 24 KB packet cap)
                +-- Ollama client (configured localhost only; 8k context, 1536 output tokens)
                +-- Output validator (JSON, exact evidence IDs, bounded fields)
```

## Trust boundaries

- Process names and returned event data are untrusted, prompt-injected input. They are JSON-encoded and included only as bounded evidence; system policy tells the model not to follow their text.
- Python gathers evidence and selects tools deterministically by question topic. Ollama cannot choose an unregistered name, change tool arguments, or ask the application to run shell text.
- The registry provides only read operations. It rejects unknown tools, extra argument keys, invalid IDs, out-of-range limits, and over-size results.
- Model hypotheses are kept only if their evidence IDs exist in the packet sent to the model. Model summary prose is discarded. A malformed or ungrounded response becomes `INCONCLUSIVE`.
- The Ollama request caps context and generation for the 6 GB GPU target. If structured output is malformed, the investigator retries once with the same packet and a concise repair instruction; validation remains strict.
- The UI renders collector-created measurements as observed facts, model statements as hypotheses, and story narration under a separate `FICTION` label.
- Ollama's base URL must use a loopback hostname. There is no alternate inference backend.

## Data retention

SQLite stores event payloads, investigation question/result, local model tag, duration, and optional Story Mode preference. Old events and investigations are pruned at startup using `history_retention_days`. Rotating diagnostic logs share the application-data directory and exclude prompts and telemetry payloads. Raw system logs and command lines are never collected. `phantom clear-history` clears all local records and preferences.

When the configured database cannot be opened, the CLI reports session-only history and uses an in-memory SQLite database so telemetry can continue. Event insert failures during monitoring are reported without terminating sampling.

## Deliberate implementation choice

This MVP uses a straight-line Python workflow instead of LangGraph. It has no model-directed tool calls, so a graph would add dependency and state machinery without improving the current bounded flow. The detector, registry, evidence packet, inference client, storage, and terminal presentation remain separate and replaceable modules.
