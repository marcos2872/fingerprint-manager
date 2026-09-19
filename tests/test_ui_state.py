"""backend/ui_state.py: lógica pura de labels (sem display)."""

from backend import ui_state


def test_unlock_status():
    assert ui_state.unlock_status(False, 1, True, True) == "desativado (sem leitor)"
    assert ui_state.unlock_status(True, 0, True, True) == "desativado (sem digitais)"
    assert ui_state.unlock_status(True, 2, None, None) == "desconhecido"
    assert ui_state.unlock_status(True, 1, False, False) == "desativado (PAM desligado)"
    assert ui_state.unlock_status(True, 1, True, False) == "ativado"
    assert ui_state.unlock_status(True, 1, False, True) == "ativado"


def test_pam_switch_subtitle():
    assert ui_state.pam_switch_subtitle(True) == "Desbloqueio ativado"
    assert ui_state.pam_switch_subtitle(False) == "Desbloqueio desativado"
    assert ui_state.pam_switch_subtitle(None) == "Não foi possível verificar"


def test_short():
    assert ui_state.short("abc") == "abc"
    assert ui_state.short("x" * 200) == "x" * 160 + "…"
    assert ui_state.short("x" * 160) == "x" * 160
