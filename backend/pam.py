"""Wrapper authselect (Fedora). Nunca editar /etc/pam.d na mão.

Tudo sync aqui; a UI chama via thread para não travar.
pkexec abre o diálogo de senha do sistema.
"""

from __future__ import annotations

import shutil
import subprocess

FEATURE = "with-fingerprint"
BACKUP = "pre-fprint"


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
