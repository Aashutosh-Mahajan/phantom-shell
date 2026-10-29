from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request
from typing import Any


class _LocalOnlyRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Do not let a loopback Ollama server redirect prompts off-machine.
        return None


class Ollama:
    def __init__(self, base_url: str, model: str, timeout: int = 90):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _LocalOnlyRedirectHandler())

    def _get(self, path: str) -> dict[str, Any]:
        request = urllib.request.Request(f"{self.base_url}{path}")
        with self._opener.open(request, timeout=min(self.timeout, 5)) as response:
            return json.loads(response.read(1_000_000))

    def status(self) -> tuple[bool, str]:
        try:
            models = self._get("/api/tags").get("models", [])
            names = {model.get("name") for model in models}
            if self.model not in names:
                return False, f"Ollama is running, but model '{self.model}' is not installed. Run: ollama pull {self.model}"
            return True, f"Ollama is running; model tag is installed: {self.model} | {self.base_url}"
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            return False, f"Cannot reach local Ollama at {self.base_url}: {exc}. Start Ollama and verify the configured URL."

    def generate(self, prompt: str, schema: dict[str, Any] | None = None) -> str:
        # Keep Ollama from reserving Gemma's 131k default context on the
        # project's 6 GB GPU target. The evidence packet is capped at 24 KB.
        body_data: dict[str, Any] = {"model": self.model, "prompt": prompt, "stream": False, "options": {"num_ctx": 8192, "num_predict": 1536, "temperature": 0}}
        if schema is not None:
            body_data["format"] = schema
        body = json.dumps(body_data).encode()
        request = urllib.request.Request(f"{self.base_url}/api/generate", data=body, headers={"Content-Type": "application/json"})
        try:
            with self._opener.open(request, timeout=self.timeout) as response:
                result = json.loads(response.read(1_000_000))
            return str(result.get("response", "")).strip()
        except (socket.timeout, TimeoutError) as exc:
            raise TimeoutError(f"Local model exceeded the {self.timeout}s inference limit") from exc
        except urllib.error.HTTPError as exc:
            try:
                detail = json.loads(exc.read(4096)).get("error", str(exc))
            except (ValueError, AttributeError):
                detail = str(exc)
            raise RuntimeError(f"Local Ollama inference failed ({exc.code}): {str(detail)[:500]}") from exc
        except (urllib.error.URLError, ValueError) as exc:
            raise RuntimeError(f"Local model inference failed: {exc}") from exc
