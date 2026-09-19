"""Leitura PAM por serviço (backend/pam.py) com fixtures em tmp dir.

Cobre: include/substack, comentários, include quebrado -> None,
loop entre arquivos, arquivo ausente -> None, labels.
"""

import pytest

from backend import pam


@pytest.fixture()
def pamdir(tmp_path, monkeypatch):
    d = tmp_path / "pam.d"
    d.mkdir()
    monkeypatch.setattr(pam, "PAM_DIR", str(d))
    return d


def _write(pamdir, name, content):
    (pamdir / name).write_text(content, encoding="utf-8")


def test_sudo_ativo_via_system_auth(pamdir):
    _write(pamdir, "sudo", "auth include system-auth\n")
    _write(
        pamdir,
        "system-auth",
        "auth sufficient pam_unix.so nullok\n"
        "auth sufficient pam_fprintd.so\n",
    )
    assert pam.sudo_fingerprint_active() is True


def test_sudo_inativo(pamdir):
    _write(pamdir, "sudo", "auth include system-auth\n")
    _write(pamdir, "system-auth", "auth sufficient pam_unix.so nullok\n")
    assert pam.sudo_fingerprint_active() is False


def test_login_precisa_dos_dois_arquivos(pamdir):
    _write(pamdir, "gdm-fingerprint", "auth sufficient pam_fprintd.so\n")
    _write(pamdir, "gdm-password", "auth substack password-auth\n")
    _write(pamdir, "password-auth", "auth sufficient pam_unix.so\n")
    # só um dos dois tem -> não conta como ativo (toggle religa o outro)
    assert pam.login_fingerprint_active() is False
    _write(
        pamdir,
        "gdm-password",
        "auth sufficient pam_fprintd.so\nauth substack password-auth\n",
    )
    assert pam.login_fingerprint_active() is True


def test_include_quebrado_vira_desconhecido(pamdir):
    _write(pamdir, "sudo", "auth include system-auth\n")
    # system-auth não existe -> None (desconhecido, não "inativo")
    assert pam.sudo_fingerprint_active() is None


def test_arquivo_ausente_vira_desconhecido(pamdir):
    assert pam.sudo_fingerprint_active() is None


def test_comentarios_ignorados_e_loop_nao_trava(pamdir):
    _write(pamdir, "sudo", "# auth sufficient pam_fprintd.so\n" "auth include loop-a\n")
    _write(pamdir, "loop-a", "auth include loop-b\n")
    _write(pamdir, "loop-b", "auth include loop-a\n")
    assert pam.sudo_fingerprint_active() is False


def test_is_enabled_compat(pamdir):
    _write(pamdir, "sudo", "auth sufficient pam_fprintd.so\n")
    _write(pamdir, "gdm-fingerprint", "auth sufficient pam_unix.so\n")
    _write(pamdir, "gdm-password", "auth sufficient pam_unix.so\n")
    assert pam.is_enabled() is True
    _write(pamdir, "sudo", "auth sufficient pam_unix.so\n")
    assert pam.is_enabled() is False


def test_current_profile_sem_authselect(monkeypatch):
    monkeypatch.setattr(pam, "has_authselect", lambda: False)
    ok, _ = pam.current_profile_text()
    assert ok is False
