"""backend/version.py: comparação e busca de release com rede mockada."""

import io
import json
import urllib.error

from backend import version as v


def test_is_newer():
    assert v.is_newer("v1.0.1", "1.0.0") is True
    assert v.is_newer("1.1.0", "1.0.0") is True
    assert v.is_newer("v" + v.APP_VERSION) is False
    assert v.is_newer("v0.9.9") is False
    assert v.is_newer("abc") is False
    assert v.is_newer("") is False


class FakeResp:
    def __init__(self, payload: bytes):
        self._io = io.BytesIO(payload)

    def __enter__(self):
        return self._io

    def __exit__(self, *a):
        return False


def test_fetch_latest_nova(monkeypatch):
    payload = json.dumps(
        {"tag_name": "v9.9.9", "html_url": "https://x/y"}
    ).encode()
    monkeypatch.setattr(
        "urllib.request.urlopen", lambda *a, **k: FakeResp(payload)
    )
    assert v.fetch_latest() == ("v9.9.9", "https://x/y")


def test_fetch_latest_sem_tag_vira_none(monkeypatch):
    payload = json.dumps({"html_url": "https://x/y"}).encode()
    monkeypatch.setattr(
        "urllib.request.urlopen", lambda *a, **k: FakeResp(payload)
    )
    assert v.fetch_latest() is None


def test_fetch_latest_erro_de_rede_vira_none(monkeypatch):
    def boom(*a, **k):
        raise urllib.error.URLError("sem rede")

    monkeypatch.setattr("urllib.request.urlopen", boom)
    assert v.fetch_latest() is None


def test_fetch_latest_404_vira_none(monkeypatch):
    def boom(*a, **k):
        raise urllib.error.HTTPError("url", 404, "not found", {}, None)

    monkeypatch.setattr("urllib.request.urlopen", boom)
    assert v.fetch_latest() is None


def test_fetch_latest_json_invalido_vira_none(monkeypatch):
    monkeypatch.setattr(
        "urllib.request.urlopen", lambda *a, **k: FakeResp(b"nao-json")
    )
    assert v.fetch_latest() is None
