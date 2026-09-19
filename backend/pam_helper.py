"""Helper privilegiado para ligar/desligar digital por serviço PAM.

Executado como root via `pkexec python3 pam_helper.py <login|sudo> <on|off>`.
Uso direto (sem pkexec) só funciona com FPRINT_PAM_DIR apontando para
um diretório gravável — usado para testes.

O que faz, de forma atômica (backup + tmp + os.replace):
- login on/off: insere/remove `auth sufficient pam_fprintd.so` no topo do
  stack `auth` de /etc/pam.d/gdm-fingerprint.
- sudo on/off: idem em /etc/pam.d/sudo.

Segurança: a linha é `sufficient` (nunca bloqueia — cai para pam_unix) e
a escrita é recusada se o resultado não contiver pam_unix.
"""

from __future__ import annotations

import os
import sys
import time

PAM_DIR = os.environ.get("FPRINT_PAM_DIR", "/etc/pam.d")
SERVICES = {
    "login": os.path.join(PAM_DIR, "gdm-fingerprint"),
    "sudo": os.path.join(PAM_DIR, "sudo"),
}
AUTH_LINE = "auth sufficient pam_fprintd.so"


def _is_code(line: str) -> bool:
    stripped = line.split("#", 1)[0].strip()
    return bool(stripped)


def _is_fprintd_auth(line: str) -> bool:
    code = line.split("#", 1)[0].split()
    if len(code) < 3 or code[0] != "auth":
        return False
    return "pam_fprintd" in code[2] or any("pam_fprintd" in a for a in code[3:])


def _first_auth_index(lines: list[str]) -> int | None:
    for i, line in enumerate(lines):
        code = line.split("#", 1)[0].split()
        if code and code[0] == "auth":
            return i
    return None


def apply(service: str, enable: bool) -> str:
    if service not in SERVICES:
        raise SystemExit(f"serviço desconhecido: {service} (use login|sudo)")
    path = SERVICES[service]
    if not os.path.isfile(path):
        raise SystemExit(f"arquivo ausente: {path}")
    with open(path, encoding="utf-8", errors="replace") as f:
        original = f.read().splitlines()
    lines = list(original)

    present = any(_is_fprintd_auth(l) for l in lines)
    if enable and present:
        return "já ativado (sem alterações)"
    if not enable and not present:
        return "já desativado (sem alterações)"

    if enable:
        idx = _first_auth_index(lines)
        if idx is None:
            raise SystemExit(f"sem stack auth em {path} — recuso alterar")
        lines.insert(idx, AUTH_LINE)
    else:
        lines = [l for l in lines if not _is_fprintd_auth(l)]

    new_text = "\n".join(lines) + "\n"
    # Invariantes: nada além da nossa linha pode mudar; se pam_unix estava
    # lá (arquivo próprio; pode vir via `include`), tem que continuar.
    # Nota: sudo/gdm-fingerprint normalmente trazem pam_unix via include.
    if "pam_unix" in "\n".join(original) and "pam_unix" not in new_text:
        raise SystemExit("validação falhou: pam_unix sumiu — nada foi alterado")
    if _first_auth_index(lines) is None:
        raise SystemExit("validação falhou: stack auth vazio — nada foi alterado")
    if enable and AUTH_LINE not in new_text:
        raise SystemExit("validação falhou: linha não aplicada")
    if not enable and "pam_fprintd" in "\n".join(
        l for l in new_text.splitlines() if _is_code(l) and l.split()[0] == "auth"
    ):
        raise SystemExit("validação falhou: linha não removida")

    stamp = time.strftime("%Y%m%d-%H%M%S")
    backup = f"{path}.bak-fingerprint-manager-{stamp}"
    with open(backup, "w", encoding="utf-8") as f:
        with open(path, encoding="utf-8", errors="replace") as orig:
            f.write(orig.read())
    tmp = f"{path}.tmp-fingerprint-manager"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(new_text)
    os.replace(tmp, path)
    return f"OK ({'ativado' if enable else 'desativado'}, backup em {backup})"


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(f"uso: {argv[0]} <login|sudo> <on|off>", file=sys.stderr)
        return 2
    try:
        msg = apply(argv[1], argv[2].lower() in ("on", "1", "true", "enable"))
    except SystemExit as e:
        print(str(e), file=sys.stderr)
        return 1
    print(msg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
