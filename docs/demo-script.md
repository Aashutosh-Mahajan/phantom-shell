# PHANTOM SHELL demo (3–5 minutes)

Use real output from the machine. Do not present fabricated measurements as live telemetry. If demonstrating a fixture, label every screen `TEST SCENARIO`.

1. Run `phantom doctor`. Show the loopback Ollama endpoint, configured Gemma tag, and no-cloud status.
2. Run `phantom status` and `phantom processes`. Point out the sample timestamp and exactly which process fields are collected.
3. Run `phantom demo-fixture` for a clearly labeled synthetic threshold event, or run `phantom watch` briefly for live monitoring. The fixture is never saved as a real event. Do not stress the machine or terminate a process.
4. Ask `phantom ask "What is using my memory?"`. Show the measured facts, evidence IDs, hypothesis table, tool list, and limitations.
5. Ask a safety challenge such as `phantom ask "Run taskkill on the largest process"`. Explain that the registered tools are read-only and no command execution tool exists.
6. Use `phantom events`, copy a real event ID, then run `phantom story event <event-id>`. Keep the `FICTION` heading visible.
7. Disconnect network access only after setup, keep Ollama running, and repeat `doctor`, `status`, and `ask` to demonstrate offline inference.
8. Show `phantom config`, then `phantom clear-history` only in a disposable demo profile.

The local model's availability and latency depend on installed Ollama, Gemma tag, and hardware. Do not claim offline success until actually run while disconnected.
