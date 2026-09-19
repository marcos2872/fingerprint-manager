"""Janela de Enroll/Verify com Vte embutido (spec 6.1.5).

- NavigationPage separada vira Window própria porque a principal é
  PreferencesWindow (não empilha NavigationView).
- Instrução por scan-type + ProgressBar por num-enroll-stages.
- Vte readonly como log técnico. Cancelar mata o subprocesso.
"""

from __future__ import annotations

import os
import shutil
import signal

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Vte", "3.91")
from gi.repository import Adw, GLib, Gtk, Vte  # noqa: E402


class EnrollWindow(Adw.Window):
    def __init__(self, parent, title: str, argv: list[str], stages: int = 5,
                 instruction: str = "", on_done=None):
        super().__init__(transient_for=parent, modal=False)
        self.set_title(title)
        self.set_default_size(620, 420)
        self.argv = argv
        self.on_done = on_done
        self._child_pid: int | None = None
        self._done_called = False

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_top(16)
        box.set_margin_bottom(16)
        box.set_margin_start(16)
        box.set_margin_end(16)

        self.info = Gtk.Label(label=instruction or "Siga as instruções no terminal abaixo.")
        self.info.set_wrap(True)
        self.info.add_css_class("title-2")
        box.append(self.info)

        self.progress = Gtk.ProgressBar()
        self.progress.set_show_text(True)
        self.progress.set_fraction(0.0)
        self.progress.set_text(f"0/{stages}")
        self._stages = max(stages, 1)
        box.append(self.progress)

        self.term = Vte.Terminal()
        self.term.set_input_enabled(False)
        scrolled = Gtk.ScrolledWindow(hexpand=True, vexpand=True)
        scrolled.set_min_content_height(180)
        scrolled.set_child(self.term)
        box.append(scrolled)

        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        actions.set_halign(Gtk.Align.END)
        self.btn_cancel = Gtk.Button(label="Cancelar")
        self.btn_done = Gtk.Button(label="Concluir")
        self.btn_done.add_css_class("suggested-action")
        self.btn_done.set_sensitive(False)
        self.btn_cancel.connect("clicked", lambda *_: self._cancel())
        self.btn_done.connect("clicked", lambda *_: self._finish(True))
        actions.append(self.btn_cancel)
        actions.append(self.btn_done)
        box.append(actions)

        self.set_content(box)
        self.connect("close-request", self._on_close)
        self.term.connect("child-exited", self._on_child_exited)
        GLib.idle_add(self._spawn)

    def _spawn(self):
        binary = shutil.which(self.argv[0]) if self.argv else None
        if not binary:
            self.info.set_text(f"Comando não encontrado: {self.argv[0] if self.argv else '?'}")
            self.btn_done.set_sensitive(True)
            return False
        argv = [binary, *self.argv[1:]]
        try:
            # spawn_async é assíncrono de verdade: retorna void, pid vem no callback.
            self.term.spawn_async(
                Vte.PtyFlags.DEFAULT,
                os.path.expanduser("~"),
                argv,
                None,
                GLib.SpawnFlags.SEARCH_PATH,
                None,
                None,
                10000,
                None,
                self._on_spawned,
                None,
            )
        except Exception as e:
            self.info.set_text(f"Falha ao iniciar: {e}")
            self.btn_done.set_sensitive(True)
        return False

    def _on_spawned(self, _term, pid: int, error, _data):
        if error is not None:
            try:
                msg = error.message
            except Exception:
                msg = str(error)
            self.info.set_text(f"Falha ao iniciar: {msg}")
            self.btn_done.set_sensitive(True)
            return
        self._child_pid = pid

    def _on_child_exited(self, _term, status: int):
        self._child_pid = None
        ok = (status == 0)
        try:
            # heurística simples de progresso: sucesso = cheio
            self.progress.set_fraction(1.0 if ok else self.progress.get_fraction())
            self.progress.set_text(f"{self._stages}/{self._stages}" if ok else "falhou")
        except Exception:
            pass
        self.btn_done.set_sensitive(True)
        self._exit_ok = ok
        if ok:
            self.info.set_text("Concluído com sucesso. Clique em Concluir.")
        else:
            self.info.set_text("Falhou ou foi cancelado. Veja o log acima e tente de novo.")

    def _cancel(self):
        try:
            if self._child_pid:
                os.kill(self._child_pid, signal.SIGTERM)
        except Exception:
            pass
        self._finish(False)

    def _on_close(self, *_):
        # Se processo vivo, confirma
        if self._child_pid and not self.btn_done.is_sensitive():
            dlg = Adw.AlertDialog.new("Cancelar operação?", "O processo em andamento será interrompido.")
            dlg.add_response("keep", "Continuar")
            dlg.add_response("stop", "Cancelar operação")
            dlg.set_response_appearance("stop", Adw.ResponseAppearance.DESTRUCTIVE)
            dlg.set_default_response("keep")
            dlg.choose(self, None, self._on_confirm_close, None)
            return True
        self._finish(False)
        return False

    def _on_confirm_close(self, dlg, _res, _data):
        if dlg.choose_finish(_res) == "stop":
            self._cancel()
        # senão mantém aberta

    def _finish(self, ok: bool):
        if self._done_called:
            try:
                self.close()
            except Exception:
                pass
            return
        self._done_called = True
        cb = self.on_done
        try:
            self.close()
        except Exception:
            pass
        if cb:
            GLib.idle_add(cb, ok)
