"""Wrapper authselect (Fedora). Nunca editar /etc/pam.d na mão.

Tudo sync aqui; a UI chama via thread para não travar.
pkexec abre o diálogo de senha do sistema.

Por que não há toggle login-vs-sudo separado: o authselect expõe um único
knob (`with-fingerprint`) que alimenta `system-auth` (sudo, su, login console)
e `fingerprint-auth` (GDM). Separar de verdade exigiria editar /etc/pam.d na
mão — o authselect sobrescreve no próximo apply e um erro trava o login.
Por isso a escrita é só pelo master switch e o por-serviço é leitura.
"""

from __future__ import annotations

import os
import shutil
import subprocess

FEATURE = "with-fingerprint"
BACKUP = "pre-fprint"
PAM_DIR = "/etc/pam.d"


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
    """True se with-fingerprint ativo."""
    if not has_authselect():
        return False
    ok, out = current_profile_text()
    if not ok:
        return False
    if FEATURE in out:
        return True
    # fallback: is-feature-enabled (código 0 = ativo em algumas versões)
    ok2, _ = _run(["authselect", "is-feature-enabled", FEATURE])
    return ok2


def set_enabled(enable: bool) -> tuple[bool, str]:
    """Liga/desliga com backup + apply-changes. Usa pkexec."""
    if not has_authselect():
        return False, "authselect não disponível neste sistema."
    action = "enable-feature" if enable else "disable-feature"
    ok, out = _run(
        ["pkexec", "authselect", action, FEATURE, f"--backup={BACKUP}"]
    )
    if not ok:
        return False, out or "Falha ao alterar feature (polkit cancelado?)."
    ok2, out2 = _run(["pkexec", "authselect", "apply-changes", "-b"])
    if not ok2:
        return False, out2 or "Falha em apply-changes."
    return True, out2 or "OK"


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


def sudo_fingerprint_active() -> bool | None:
    """sudo resolve para system-auth; None = não foi possível determinar."""
    return _stack_uses_fprintd("sudo")


def login_fingerprint_active() -> bool | None:
    """Login gráfico (GDM) resolve para fingerprint-auth."""
    res = _stack_uses_fprintd("gdm-fingerprint")
    if res is None:
        res = _stack_uses_fprintd("fingerprint-auth")
    if res is None:
        res = _stack_uses_fprintd("login")
    return res


def service_label(active: bool | None) -> str:
    if active is True:
        return "Ativo"
    if active is False:
        return "Inativo"
    return "Desconhecido"
