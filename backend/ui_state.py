"""Lógica pura de apresentação (sem GTK): decisão de labels e estados.

Tudo aqui é função pura e testável sem display. A janela
(`ui/window.py`) apenas exibe o que estas funções decidem.
"""

from __future__ import annotations


def unlock_status(
    has_reader: bool,
    enrolled_count: int,
    login_active: bool | None,
    sudo_active: bool | None,
) -> str:
    """Estado do desbloqueio para a página Dispositivo."""
    if not has_reader:
        return "desativado (sem leitor)"
    if enrolled_count == 0:
        return "desativado (sem digitais)"
    if login_active is None and sudo_active is None:
        return "desconhecido"
    if login_active is True or sudo_active is True:
        return "ativado"
    return "desativado (PAM desligado)"


def pam_switch_subtitle(active: bool | None) -> str:
    """Subtitle dos switches login/sudo na página Desbloqueio."""
    if active is None:
        return "Não foi possível verificar"
    return "Desbloqueio ativado" if active else "Desbloqueio desativado"


def short(text: str, limit: int = 160) -> str:
    """Trunca texto longo de subtitle com elipse."""
    return (text[:limit] + "…") if len(text) > limit else text
