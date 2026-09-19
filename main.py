"""App GTK4/Adwaita — single-instance."""

from __future__ import annotations

import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib  # noqa: E402

from ui.window import ManagerWindow

from backend.version import APP_ID


class FingerprintApp(Adw.Application):
    def __init__(self):
        super().__init__(
            application_id=APP_ID,
            flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE,
        )
        self._window: ManagerWindow | None = None
        # --background é obsoleto (era do tray, removido): aceito como
        # no-op para não quebrar arquivos antigos de autostart que
        # ainda passam a flag. É ignorado.
        self.add_main_option(
            "background",
            ord("b"),
            GLib.OptionFlags.NONE,
            GLib.OptionArg.NONE,
            "Obsoleto (ignorado)",
            None,
        )

    def do_command_line(self, cmdline):
        cmdline.get_options_dict().end().unpack()  # aceita e ignora
        self.activate()
        if self._window:
            self._window.present()
        return 0

    def do_activate(self):
        if self._window is None:
            self._window = ManagerWindow(self)
        self._window.present()


def main() -> int:
    app = FingerprintApp()
    return app.run(sys.argv)


if __name__ == "__main__":
    raise SystemExit(main())
