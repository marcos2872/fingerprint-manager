"""Helper privilegiado (backend/pam_helper.py) com fixtures em tmp dir.

NUNCA toca /etc/pam.d aqui: SERVICES é sobrescrito para arquivos temporários.
Cobre os invariantes de segurança: idempotência, multi-arquivo, recusas,
backup e escrita atômica.
"""

import os

import pytest

from backend import pam_helper


@pytest.fixture()
def svc(tmp_path, monkeypatch):
    d = tmp_path / "pam.d"
    d.mkdir()
    sudo = d / "sudo"
    login = d / "gdm-fingerprint"
    lock = d / "gdm-password"
    sudo.write_text(
        "#%PAM-1.0\nauth include system-auth\naccount include system-auth\n",
        encoding="utf-8",
    )
    login.write_text(
        "auth substack fingerprint-auth\nauth include postlogin\n", encoding="utf-8"
    )
    lock.write_text(
        "auth substack password-auth\nauth include postlogin\n", encoding="utf-8"
    )
    monkeypatch.setattr(
        pam_helper,
        "SERVICES",
        {"login": [str(login), str(lock)], "sudo": [str(sudo)]},
    )
    return {"sudo": sudo, "login": [login, lock]}


def _backups(path):
    parent = os.path.dirname(path)
    base = os.path.basename(path)
    return [f for f in os.listdir(parent) if f.startswith(base + ".bak-")]


def test_sudo_on_off_idempotente(svc):
    assert "ativado" in pam_helper.apply("sudo", True)
    content = svc["sudo"].read_text(encoding="utf-8")
    assert content.splitlines()[1] == pam_helper.AUTH_LINE  # topo do stack auth
    assert "já ativado" in pam_helper.apply("sudo", True)
    assert "desativado" in pam_helper.apply("sudo", False)
    assert "pam_fprintd" not in svc["sudo"].read_text(encoding="utf-8")
    assert "já desativado" in pam_helper.apply("sudo", False)


def test_login_mexe_nos_dois_arquivos(svc):
    pam_helper.apply("login", True)
    for f in svc["login"]:
        assert pam_helper.AUTH_LINE in f.read_text(encoding="utf-8")
    pam_helper.apply("login", False)
    for f in svc["login"]:
        assert "pam_fprintd" not in f.read_text(encoding="utf-8")


def test_backup_e_sem_tmp_restante(svc):
    pam_helper.apply("sudo", True)
    assert len(_backups(str(svc["sudo"]))) == 1
    parent = os.path.dirname(str(svc["sudo"]))
    assert not [f for f in os.listdir(parent) if ".tmp-fingerprint-manager" in f]


def test_recusa_sem_stack_auth(tmp_path, monkeypatch):
    odd = tmp_path / "odd"
    odd.write_text("# só comentários\naccount include x\n", encoding="utf-8")
    monkeypatch.setattr(pam_helper, "SERVICES", {"odd": [str(odd)]})
    with pytest.raises(SystemExit):
        pam_helper.apply("odd", True)
    assert "pam_fprintd" not in odd.read_text(encoding="utf-8")


def test_recusa_arquivo_ausente(tmp_path, monkeypatch):
    monkeypatch.setattr(
        pam_helper, "SERVICES", {"ghost": [str(tmp_path / "nao-existe")]}
    )
    with pytest.raises(SystemExit):
        pam_helper.apply("ghost", True)


def test_recusa_servico_desconhecido():
    with pytest.raises(SystemExit):
        pam_helper.apply("foo", True)


def test_preserva_resto_do_arquivo(svc):
    before = svc["sudo"].read_text(encoding="utf-8").splitlines()
    pam_helper.apply("sudo", True)
    pam_helper.apply("sudo", False)
    after = svc["sudo"].read_text(encoding="utf-8").splitlines()
    assert before == after
