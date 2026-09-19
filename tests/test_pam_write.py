"""Escrita via backend/pam.py sem pkexec (FPRINT_PAM_DIR em tmp dir)."""

import pytest

from backend import pam


@pytest.fixture()
def pamdir(tmp_path, monkeypatch):
    d = tmp_path / "pam.d"
    d.mkdir()
    for name in ("sudo", "gdm-fingerprint", "gdm-password"):
        (d / name).write_text(
            "auth include system-auth\naccount include system-auth\n",
            encoding="utf-8",
        )
    monkeypatch.setenv("FPRINT_PAM_DIR", str(d))
    return d


def test_set_service_enabled_sem_pkexec(pamdir):
    ok, msg = pam.set_service_enabled("sudo", True)
    assert ok is True
    assert "pam_fprintd" in (pamdir / "sudo").read_text(encoding="utf-8")
    ok, _ = pam.set_service_enabled("sudo", False)
    assert ok is True
    assert "pam_fprintd" not in (pamdir / "sudo").read_text(encoding="utf-8")


def test_set_service_desconhecido():
    ok, msg = pam.set_service_enabled("foo", True)
    assert ok is False
    assert "desconhecido" in msg


def test_falha_do_helper_vira_false(pamdir, monkeypatch):
    (pamdir / "sudo").unlink()  # helper vai recusar: arquivo ausente
    ok, msg = pam.set_service_enabled("sudo", True)
    assert ok is False
    assert msg
