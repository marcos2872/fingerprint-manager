"""UI (opt-in): só roda com display + RUN_GUI_TESTS=1.

Sem display (CI/headless sem Xvfb) estes testes são pulados.
Cobre as labels de desbloqueio da página Dispositivo/Desbloqueio
com backends mockados — sem D-Bus, rede ou /etc/pam.d reais.
"""

import os

import pytest

gi = pytest.importorskip("gi")
try:
    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    from gi.repository import Adw, GLib, Gtk  # noqa: E402
    from ui.window import ManagerWindow  # noqa: E402

    _UI_IMPORT_OK = True
except (ImportError, ValueError):
    # Sem typelibs (ex: Vte) ou sem GTK: os testes são pulados.
    ManagerWindow = None  # type: ignore
    _UI_IMPORT_OK = False

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_GUI_TESTS") != "1" or not _UI_IMPORT_OK,
    reason="UI: requer display e typelibs GTK/Vte (rode com RUN_GUI_TESTS=1)",
)
from backend import fprintd, pam  # noqa: E402
from backend import version as version_mod  # noqa: E402
# Adw/GLib/Gtk/ManagerWindow vieram do try acima; o skipif cobre a falta.


@pytest.fixture()
def window(monkeypatch):
    if not Gtk.init_check():
        pytest.skip("Gtk não inicializou (sem display)")
    monkeypatch.setattr(fprintd, "get_devices", lambda: [])
    monkeypatch.setattr(fprintd, "resolve_device", lambda *a, **k: None)
    monkeypatch.setattr(pam, "current_profile_text", lambda: (True, "local"))
    monkeypatch.setattr(pam, "sudo_fingerprint_active", lambda: False)
    monkeypatch.setattr(pam, "login_fingerprint_active", lambda: False)
    monkeypatch.setattr(version_mod, "fetch_latest", lambda *a, **k: None)
    monkeypatch.setattr(GLib, "timeout_add_seconds", lambda *a, **k: 0)
    app = Adw.Application(application_id="org.example.Test")
    w = ManagerWindow(app)
    yield w
    try:
        w.close()
    except Exception:
        pass


def _state(window, enrolled, login, sudo):
    window._devices = ["/d"]
    window._device_path = "/d"
    window._props = {"name": "X", "scan-type": "press", "num-enroll-stages": 5}
    window._device_labels = {"/d": "X"}
    window._enrolled = enrolled
    window._login_active = login
    window._sudo_active = sudo
    window._pam_text = "t"
    window._render_all()


def test_unlock_ativado(window):
    _state(window, ["right-index-finger"], True, False)
    assert window.row_unlock.get_subtitle() == "ativado"
    assert window.switch_login.get_subtitle() == "Desbloqueio ativado"
    assert window.switch_sudo.get_subtitle() == "Desbloqueio desativado"


def test_unlock_sem_digitais(window):
    _state(window, [], True, True)
    assert window.row_unlock.get_subtitle() == "desativado (sem digitais)"


def test_unlock_pam_desligado(window):
    _state(window, ["right-index-finger"], False, False)
    assert window.row_unlock.get_subtitle() == "desativado (PAM desligado)"


def test_unlock_sem_leitor(window):
    window._devices = []
    window._device_path = None
    window._props = {}
    window._device_labels = {}
    window._enrolled = []
    window._login_active = True
    window._sudo_active = False
    window._pam_text = "t"
    window._render_all()
    assert window.row_unlock.get_subtitle() == "desativado (sem leitor)"


def test_versao_exibida(window):
    assert version_mod.APP_VERSION in window.row_version.get_subtitle()
