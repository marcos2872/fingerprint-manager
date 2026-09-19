"""PAM por serviço (login GDM vs sudo, independentes).

Leitura: segue `include`/`substack` de /etc/pam.d até `pam_fprintd`
(somente leitura, sem root).

Escrita: insere/remove `auth sufficient pam_fprintd.so` nos arquivos do
próprio serviço via helper privilegiado (`pkexec python3 pam_helper.py`):
login = /etc/pam.d/gdm-fingerprint (tela de login) + /etc/pam.d/gdm-password
(tela de bloqueio); sudo = /etc/pam.d/sudo. `sufficient`
nunca trava o login: se a digital falhar, cai para `pam_unix`.
O helper faz backup + validação antes de trocar o arquivo.

O switch master do authselect (`with-fingerprint`) foi removido: ele
controlava os dois juntos e impedia o controle individual.
`authselect current` segue exibido como detalhe do sistema.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys

PAM_DIR = os.environ.get("FPRINT_PAM_DIR", "/etc/pam.d")
SERVICE_FILES = {
    # login = tela de login (gdm-fingerprint) + tela de bloqueio (gdm-password)
    "login": ["gdm-fingerprint", "gdm-password"],
    "sudo": ["sudo"],
}
HELPER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pam_helper.py")
# pkexec pode esperar o usuário digitar a senha com calma.
PKEXEC_TIMEOUT_S = 120


def has_authselect() -> bool:
    return shutil.which("authselect") is not None


def _run(argv: list[str], timeout: int = 30) -> tuple[bool, str]:
    try:
        p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
        out = (p.stdout or "") + (p.stderr or "")
        return p.returncode == 0, out.strip()
    except FileNotFoundError as e:
        return False, str(e)
    except subprocess.TimeoutExpired:
        return False, "timeout"


def current_profile_text() -> tuple[bool, str]:
    """`authselect current`. ok=False se sem authselect."""
    if not has_authselect():
        return False, "authselect não encontrado (ex. Ubuntu usa pam-auth-update)."
    return _run(["authselect", "current"])


def is_enabled() -> bool:
    """Compat: True se digital ativa em login OU sudo (switch master removido)."""
    return sudo_fingerprint_active() is True or login_fingerprint_active() is True


def set_service_enabled(service: str, enable: bool) -> tuple[bool, str]:
    """Liga/desliga a digital só para um serviço, via helper com pkexec."""
    if service not in SERVICE_FILES:
        return False, f"serviço desconhecido: {service}"
    try:
        argv = [sys.executable, HELPER, service, "on" if enable else "off"]
        if not os.environ.get("FPRINT_PAM_DIR"):
            argv = ["pkexec", *argv]
        p = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=PKEXEC_TIMEOUT_S,
        )
    except FileNotFoundError as e:
        return False, str(e)
    except subprocess.TimeoutExpired:
        return False, "timeout"
    out = ((p.stdout or "") + (p.stderr or "")).strip()
    if p.returncode != 0:
        if "dismissed" in out.lower() or "cancel" in out.lower() or not out:
            return False, "polkit cancelado"
        return False, out or "Falha ao alterar o serviço."
    return True, out or "OK"


# --- Status por serviço (somente leitura) -------------------------------


def _pam_lines(service: str) -> list[str] | None:
    """Linhas não-comentadas de /etc/pam.d/<service>. None se não existir."""
    path = os.path.join(PAM_DIR, service)
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            out = []
            for raw in f:
                line = raw.split("#", 1)[0].strip()
                if line:
                    out.append(line)
            return out
    except OSError:
        return None


def _stack_uses_fprintd(service: str, _seen: set[str] | None = None) -> bool | None:
    """Segue `include`/`substack` e diz se o stack auth efetivo tem pam_fprintd.

    Retorna None quando o serviço (ou toda a cadeia) não existe = desconhecido.
    """
    if _seen is None:
        _seen = set()
    if service in _seen:
        return False
    _seen.add(service)
    lines = _pam_lines(service)
    if lines is None:
        return None
    unknown_chain = False
    for line in lines:
        parts = line.split()
        if len(parts) < 3:
            continue
        # auth <controle> <módulo> [args...]
        # ex.: "auth sufficient pam_fprintd.so" ou "auth include system-auth"
        kind, control, module = parts[0], parts[1], parts[2]
        args = parts[3:]
        if kind != "auth":
            continue
        if "pam_fprintd" in module or any("pam_fprintd" in a for a in args):
            return True
        if control in ("include", "substack"):
            sub = _stack_uses_fprintd(module, _seen)
            if sub is True:
                return True
            if sub is None:
                unknown_chain = True
    # Arquivo existe: sem pam_fprintd é Inativo; include quebrado = Desconhecido.
    return None if unknown_chain else False


def _service_active(files: list[str]) -> bool | None:
    """True se TODOS os arquivos têm digital; None se algum é desconhecido."""
    results = [_stack_uses_fprintd(f) for f in files]
    if all(r is True for r in results):
        return True
    if any(r is None for r in results):
        return None
    return False


def sudo_fingerprint_active() -> bool | None:
    """sudo resolve para system-auth; None = não foi possível determinar."""
    return _service_active(SERVICE_FILES["sudo"])


def login_fingerprint_active() -> bool | None:
    """Login gráfico: tela de login (gdm-fingerprint) + bloqueio (gdm-password)."""
    return _service_active(SERVICE_FILES["login"])
