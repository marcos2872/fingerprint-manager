"""Botão GitHub da Ajuda: asset simbólico + REPO_URL (headless)."""

from pathlib import Path

import pytest

from backend import version as v

REPO_ROOT = Path(__file__).resolve().parent.parent
SVG = REPO_ROOT / "assets" / "github-mark-symbolic.svg"


def test_repo_url_aponta_para_o_github():
    assert v.REPO_URL == f"https://github.com/{v.GITHUB_REPO}"
    assert v.REPO_URL.startswith("https://github.com/")


def test_asset_octocat_existe_e_e_simbolico():
    assert SVG.is_file(), "assets/github-mark-symbolic.svg sumiu"
    txt = SVG.read_text(encoding="utf-8")
    assert "<svg" in txt
    assert "viewBox" in txt
    assert "currentColor" in txt  # herda a cor do tema (claro/escuro)
    assert "<path" in txt


def test_window_expoe_icone_e_acha_asset_dir():
    gi = pytest.importorskip("gi")
    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    from ui import window as w  # noqa: E402

    assert w.GITHUB_ICON_NAME == "github-mark-symbolic"
    assert w.GITHUB_FALLBACK_ICON
    assert w._github_asset_dir() is not None
