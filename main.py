"""App GTK4/Adwaita — single-instance, --background, tray opcional."""

from __future__ import annotations

import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib  # noqa: E402

from ui.tray import StatusNotifierTray
from ui.window import ManagerWindow

APP_ID = "org.example.fingerprint-manager"


class FingerprintApp(Adw.Application):
    def __init__(self):
        super().__init__(
            application_id=APP_ID,
            flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE,
        )
        self._tray: StatusNotifierTray | None = None
        self._window: ManagerWindow | None = None
        self.add_main_option(
            "background",
            ord("b"),
            GLib.OptionFlags.NONE,
            GLib.OptionArg.NONE,
            "Inicia minimizado (para autostart)",
            None,
        )

    def do_command_line(self, cmdline):
        opts = cmdline.get_options_dict().end().unpack()
        background = opts.get("background", False)
        self.activate()
        if background and self._window:
            # --background: registra tray e não apresenta janela
            pass
        elif self._window:
            self._window.present()
        return 0

    def do_activate(self):
        if self._window is None:
            self._tray = StatusNotifierTray()
            # settings show-tray decide se liga
            try:
                s = Gio.Settings.new(APP_ID)
                show = s.get_boolean("show-tray")
            except Exception:
                show = True
            if show:
                self._tray.start()
            self._window = ManagerWindow(self, tray=self._tray)
            self._wire_tray()
        self._window.present()

    def _wire_tray(self):
        t = self._tray
        w = self._window
        assert t is not None and w is not None
        t.on_open = lambda: GLib.idle_add(w.present)
        t.on_enroll = lambda: GLib.idle_add(w.open_enroll_chooser)
        t.on_verify = lambda: GLib.idle_add(w.open_verify)
        t.on_pam_toggle = lambda: GLib.idle_add(self._toggle_pam)
        t.on_quit = lambda: GLib.idle_add(self.quit)

    def _toggle_pam(self):
        from backend import pam as pam_mod

        w = self._window
        if w is None:
            return False
        # delega ao switch (dispara fluxo polkit com feedback)
        w.switch_pam.set_active(not w.switch_pam.get_active())
        return False

    def do_shutdown(self):
        try:
            if self._tray is not None:
                self._tray.stop()
        finally:
            super().do_shutdown()


def main() -> int:
    app = FingerprintApp()
    return app.run(sys.argv)


if __name__ == "__main__":
    raise SystemExit(main())
