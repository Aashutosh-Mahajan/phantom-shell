from __future__ import annotations

import io
import json
import urllib.error
import urllib.request

import pytest

from phantom_shell.ollama import Ollama, _LocalOnlyRedirectHandler


def test_http_inference_error_surfaces_server_detail_without_cloud_fallback():
    class FailingOpener:
        def open(self, request, timeout):
            options = json.loads(request.data)["options"]
            assert options["num_ctx"] == 8192
            assert options["num_predict"] == 1536
            raise urllib.error.HTTPError(request.full_url, 500, "Internal Server Error", {}, io.BytesIO(b'{"error":"llama-server binary not found"}'))

    client = Ollama("http://localhost:11434", "gemma3:4b")
    client._opener = FailingOpener()
    with pytest.raises(RuntimeError, match="llama-server binary not found"):
        client.generate("hello")


def test_loopback_redirects_are_refused():
    handler = _LocalOnlyRedirectHandler()
    request = urllib.request.Request("http://localhost:11434/api/generate")
    assert handler.redirect_request(request, None, 302, "Found", {}, "https://example.com") is None
