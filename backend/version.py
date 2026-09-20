"""Versão do app + checagem de release no GitHub.

Somente leitura e sempre chamada em thread (ver AGENTS.md): um GET HTTPS
com timeout curto. Falha de rede, repo sem releases ou resposta
inesperada = None (a UI trata como "não foi possível verificar",
nunca como erro).
"""

from __future__ import annotations

import json
import urllib.request

APP_VERSION = "1.2.0"
APP_ID = "io.github.marcos2872.fingerprint-manager"
GITHUB_REPO = "marcos2872/fingerprint-manager"
REPO_URL = f"https://github.com/{GITHUB_REPO}"
API_LATEST = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"


def _parse(tag: str) -> tuple[int, ...] | None:
    try:
        return tuple(int(p) for p in tag.strip().lstrip("v").split("."))
    except (ValueError, AttributeError):
        return None


def is_newer(tag: str, current: str = APP_VERSION) -> bool:
    """True se tag (ex. v1.2.0) é mais nova que a versão atual."""
    new, cur = _parse(tag), _parse(current)
    if new is None or cur is None:
        return False
    return new > cur


def fetch_latest(timeout: int = 10) -> tuple[str, str] | None:
    """Retorna (tag, html_url) da latest release, ou None."""
    try:
        req = urllib.request.Request(
            API_LATEST, headers={"User-Agent": "fingerprint-manager", "Accept": "application/vnd.github+json"}
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.load(resp)
        tag, url = data.get("tag_name"), data.get("html_url")
        if tag and url:
            return tag, url
        return None
    except Exception:
        return None
