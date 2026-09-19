"""Janela principal — spec PLANO.md 6.1.

Shell: Adw.ApplicationWindow + ToastOverlay + ToolbarView + ViewStack
(padrão Settings moderno). Motivo: Adw.PreferencesWindow (AdwWindow)
não permite titlebar custom nem Banner no topo — e a spec exige
botão Recarregar + menu ≡ no header e Banner persistente.
O conteúdo usa os mesmos componentes normativos (PreferencesPage/
Group, ActionRow/ComboRow/SwitchRow/ExpanderRow, StatusPage).

I/O sempre em thread (nunca trava UI).
"""

from __future__ import annotations

import os
import subprocess
import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gio", "2.0")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk  # noqa: E402

from backend import fprintd, pam
from ui.enroll_view import EnrollWindow

APP_ID = "org.example.fingerprint-manager"
AUTOSTART_PATH = os.path.expanduser(
    "~/.config/autostart/fingerprint-manager.desktop"
)


class _Settings:
    """GSettings com fallback em memória (dev sem schema instalado)."""

    def __init__(self):
        self._g = None
        self._mem = {"show-tray": True, "refresh": 30, "device-path": "auto"}
        try:
            schema = Gio.SettingsSchemaSource.get_default()
            if schema and schema.lookup(APP_ID, True):
                self._g = Gio.Settings.new(APP_ID)
        except Exception:
            self._g = None

    def get_boolean(self, key):
        try:
            if self._g:
                return self._g.get_boolean(key)
        except Exception:
            pass
        return bool(self._mem.get(key, False))

    def set_boolean(self, key, val):
        self._mem[key] = bool(val)
        try:
            if self._g:
                self._g.set_boolean(key, bool(val))
        except Exception:
            pass

    def get_int(self, key):
        try:
            if self._g:
                return self._g.get_int(key)
        except Exception:
            pass
        return int(self._mem.get(key, 30))

    def get_string(self, key):
        try:
            if self._g:
                return self._g.get_string(key)
        except Exception:
            pass
        return str(self._mem.get(key, "auto"))

    def set_string(self, key, val):
        self._mem[key] = str(val)
        try:
            if self._g:
                self._g.set_string(key, str(val))
        except Exception:
            pass


def run_in_thread(fn, on_done):
    def _w():
        try:
            res = fn()
        except Exception as e:  # nunca derruba UI
            res = e
        GLib.idle_add(lambda: on_done(res) or False)

    threading.Thread(target=_w, daemon=True).start()


class ManagerWindow(Adw.ApplicationWindow):
    def __init__(self, app, tray=None):
        super().__init__(application=app)
        self.app = app
        self.tray = tray
        self.settings = _Settings()
        self.set_title("Fingerprint Manager")
        self.set_default_size(880, 620)

        self._devices: list[str] = []
        self._device_path: str | None = None
        self._props: dict = {}
        self._enrolled: list[str] = []
        self._pam_enabled = False
        self._pam_text = ""
        self._loading = False
        self._block_pam_signal = False
        self._block_device_signal = False

        self._build_shell()
        self._build_pages()
        self._bind_keys()
        self._start_auto_refresh()
        self.refresh_all()

    # -- shell: header + banner + stack -------------------------------
    def _build_shell(self):
        self.toast_overlay = Adw.ToastOverlay.new()
        self.set_content(self.toast_overlay)

        self.toolbar = Adw.ToolbarView.new()
        self.toast_overlay.set_child(self.toolbar)

        header = Adw.HeaderBar.new()
        header.set_title_widget(Adw.WindowTitle.new("Fingerprint Manager", ""))
        btn_reload = Gtk.Button.new_from_icon_name("view-refresh-symbolic")
        btn_reload.set_tooltip_text("Recarregar leitores e digitais (Ctrl+R)")
        btn_reload.connect("clicked", lambda *_: self.refresh_all())
        header.pack_start(btn_reload)

        menu = Gio.Menu()
        menu.append("Abrir Ajustes do Sistema", "app.open-settings")
        menu.append("Copiar logs", "app.copy-logs")
        menu.append("Sobre", "app.about")
        app = self.get_application()
        for name, fn in (
            ("open-settings", self._act_open_settings),
            ("copy-logs", self._act_copy_logs),
            ("about", self._act_about),
        ):
            act = Gio.SimpleAction.new(name, None)
            act.connect("activate", fn)
            if app is not None:
                app.add_action(act)
        menu_btn = Gtk.MenuButton.new()
        menu_btn.set_icon_name("open-menu-symbolic")
        menu_btn.set_menu_model(menu)
        menu_btn.set_tooltip_text("Menu")
        header.pack_end(menu_btn)
        self.toolbar.add_top_bar(header)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.toolbar.set_content(content)

        self.banner = Adw.Banner.new("")
        self.banner.set_revealed(False)
        content.append(self.banner)

        self.stack = Adw.ViewStack.new()
        content.append(self.stack)

        self.switcher = Adw.ViewSwitcher.new()
        self.switcher.set_stack(self.stack)
        self.switcher.set_policy(Adw.ViewSwitcherPolicy.WIDE)
        header.set_title_widget(self.switcher)

        self.switcher_bar = Adw.ViewSwitcherBar.new()
        self.switcher_bar.set_stack(self.stack)
        self.toolbar.add_bottom_bar(self.switcher_bar)

    # -- pages -------------------------------------------------------
    def _stack_add(self, page, name, title, icon):
        self.stack.add_titled_with_icon(page, name, title, icon)

    def _build_pages(self):
        # 1. Dispositivo
        self.page_device = Adw.PreferencesPage.new()
        self._stack_add(self.page_device, "device", "Dispositivo", "hardware-usb-symbolic")

        self.grp_reader = Adw.PreferencesGroup.new()
        self.grp_reader.set_title("Leitor")
        self.page_device.add(self.grp_reader)

        self.device_model = Gtk.StringList.new(["auto (padrão)"])
        self.combo_device = Adw.ComboRow.new()
        self.combo_device.set_title("Leitor")
        self.combo_device.set_subtitle("auto usa o padrão do fprintd")
        self.combo_device.set_model(self.device_model)
        self.combo_device.connect("notify::selected", self._on_device_changed)
        self.grp_reader.add(self.combo_device)

        self.row_model = Adw.ActionRow.new()
        self.row_model.set_title("Modelo")
        self.grp_reader.add(self.row_model)
        self.row_type = Adw.ActionRow.new()
        self.row_type.set_title("Tipo")
        self.grp_reader.add(self.row_type)
        self.row_stages = Adw.ActionRow.new()
        self.row_stages.set_title("Etapas")
        self.grp_reader.add(self.row_stages)
        self.row_present = Adw.ActionRow.new()
        self.row_present.set_title("Dedo presente")
        self.grp_reader.add(self.row_present)

        self.status_no_device = Adw.StatusPage.new()
        self.status_no_device.set_icon_name("computer-fail-symbolic")
        self.status_no_device.set_title("Nenhum leitor")
        self.status_no_device.set_description(
            "Conecte um leitor ou instale o driver. "
            "Goodix precisa de libfprint-tod via COPR."
        )
        btn = Gtk.Button.new_with_label("Recarregar")
        btn.connect("clicked", lambda *_: self.refresh_all())
        self.status_no_device.set_child(btn)
        self.status_no_device.set_visible(False)
        grp_nodev_wrap = Adw.PreferencesGroup.new()
        grp_nodev_wrap.add(self.status_no_device)
        self.page_device.add(grp_nodev_wrap)
        self._grp_nodev_wrap = grp_nodev_wrap

        # 2. Digitais
        self.page_fingers = Adw.PreferencesPage.new()
        self._stack_add(self.page_fingers, "fingers", "Digitais", "fingerprint-symbolic")

        self.grp_fingers = Adw.PreferencesGroup.new()
        self.grp_fingers.set_title("0 de 10 dedos cadastrados")
        self.page_fingers.add(self.grp_fingers)

        self.finger_rows_box = Gtk.ListBox.new()
        self.finger_rows_box.set_selection_mode(Gtk.SelectionMode.NONE)
        self.finger_rows_box.add_css_class("boxed-list")
        self.grp_fingers.add(self.finger_rows_box)

        self.status_no_fingers = Adw.StatusPage.new()
        self.status_no_fingers.set_icon_name("fingerprint-symbolic")
        self.status_no_fingers.set_title("Nenhuma digital")
        self.status_no_fingers.set_description(
            "Cadastre ao menos um dedo para desbloquear com biometria."
        )
        grp_nof_wrap = Adw.PreferencesGroup.new()
        grp_nof_wrap.add(self.status_no_fingers)
        self.page_fingers.add(grp_nof_wrap)
        self._grp_nof_wrap = grp_nof_wrap

        self.grp_actions = Adw.PreferencesGroup.new()
        self.grp_actions.set_title("Ações")
        self.page_fingers.add(self.grp_actions)

        self.btn_enroll = Gtk.Button.new_with_label("Cadastrar")
        self.btn_enroll.add_css_class("suggested-action")
        self.btn_enroll.set_tooltip_text("Cadastrar nova digital")
        self.btn_enroll.connect("clicked", lambda *_: self.open_enroll_chooser())
        self.grp_actions.add(self.btn_enroll)

        self.btn_verify = Gtk.Button.new_with_label("Verificar")
        self.btn_verify.set_tooltip_text("Verificar digital cadastrada")
        self.btn_verify.connect("clicked", lambda *_: self.open_verify())
        self.grp_actions.add(self.btn_verify)

        self.btn_delete_all = Gtk.Button.new_with_label("Apagar todas")
        self.btn_delete_all.add_css_class("destructive-action")
        self.btn_delete_all.set_tooltip_text("Apaga todas as digitais do usuário")
        self.btn_delete_all.connect("clicked", lambda *_: self.confirm_delete_all())
        self.grp_actions.add(self.btn_delete_all)

        self.btn_sys_settings = Gtk.Button.new_with_label("Abrir Ajustes")
        self.btn_sys_settings.set_tooltip_text("Abrir Contas de usuário do GNOME")
        self.btn_sys_settings.connect(
            "clicked", lambda *_: self._act_open_settings(None, None)
        )
        self.grp_actions.add(self.btn_sys_settings)

        # 3. Desbloqueio (PAM)
        self.page_pam = Adw.PreferencesPage.new()
        self._stack_add(self.page_pam, "pam", "Desbloqueio", "security-high-symbolic")

        grp_pam = Adw.PreferencesGroup.new()
        grp_pam.set_title("PAM / authselect")
        self.page_pam.add(grp_pam)

        self.switch_pam = Adw.SwitchRow.new()
        self.switch_pam.set_title("Usar digital para login e sudo")
        self.switch_pam.set_subtitle("Desativado")
        self.switch_pam.connect("notify::active", self._on_pam_toggled)
        grp_pam.add(self.switch_pam)

        self.exp_pam = Adw.ExpanderRow.new()
        self.exp_pam.set_title("Detalhe do sistema")
        self.exp_pam.set_expanded(True)
        grp_pam.add(self.exp_pam)
        self.row_pam_detail = Adw.ActionRow.new()
        self.row_pam_detail.set_title("authselect current")
        btn_copy_pam = Gtk.Button.new_from_icon_name("edit-copy-symbolic")
        btn_copy_pam.set_tooltip_text("Copiar saída")
        btn_copy_pam.connect("clicked", lambda *_: self._copy_text(self._pam_text))
        self.row_pam_detail.add_suffix(btn_copy_pam)
        self.exp_pam.add_row(self.row_pam_detail)

        # 4. Tray
        self.page_tray = Adw.PreferencesPage.new()
        self._stack_add(self.page_tray, "tray", "Tray", "status-symbolic")

        grp_tray = Adw.PreferencesGroup.new()
        grp_tray.set_title("Indicador")
        self.page_tray.add(grp_tray)

        self.switch_tray = Adw.SwitchRow.new()
        self.switch_tray.set_title("Mostrar ícone na barra")
        self.switch_tray.set_subtitle("StatusNotifierItem (opcional)")
        self.switch_tray.set_active(self.settings.get_boolean("show-tray"))
        self.switch_tray.connect("notify::active", self._on_tray_toggled)
        grp_tray.add(self.switch_tray)

        self.row_host = Adw.ActionRow.new()
        self.row_host.set_title("Host StatusNotifier")
        self.row_host.set_subtitle("verificando...")
        btn_host = Gtk.Button.new_with_label("Verificar")
        btn_host.connect("clicked", lambda *_: self._update_host_row())
        self.row_host.add_suffix(btn_host)
        grp_tray.add(self.row_host)

        self.switch_autostart = Adw.SwitchRow.new()
        self.switch_autostart.set_title("Iniciar com a sessão (--background)")
        self.switch_autostart.set_active(os.path.exists(AUTOSTART_PATH))
        self.switch_autostart.connect("notify::active", self._on_autostart_toggled)
        grp_tray.add(self.switch_autostart)

        # 5. Ajuda
        self.page_help = Adw.PreferencesPage.new()
        self._stack_add(self.page_help, "help", "Ajuda", "help-about-symbolic")

        grp_help = Adw.PreferencesGroup.new()
        grp_help.set_title("Diagnóstico")
        self.page_help.add(grp_help)

        row_logs = Adw.ActionRow.new()
        row_logs.set_title("Logs")
        row_logs.set_subtitle("Últimas 200 linhas do app")
        btn_logs = Gtk.Button.new_with_label("Copiar")
        btn_logs.connect("clicked", lambda *_: self._act_copy_logs(None, None))
        row_logs.add_suffix(btn_logs)
        grp_help.add(row_logs)

        row_diag = Adw.ActionRow.new()
        row_diag.set_title("Diagnóstico do tray")
        row_diag.set_subtitle("busctl StatusNotifier + fprintd")
        btn_diag = Gtk.Button.new_with_label("Copiar")
        btn_diag.connect("clicked", lambda *_: self._copy_text(self._diag_text()))
        row_diag.add_suffix(btn_diag)
        grp_help.add(row_diag)

        row_goodix = Adw.ActionRow.new()
        row_goodix.set_title("Leitor Goodix?")
        row_goodix.set_subtitle("Precisa de libfprint-tod via COPR. Veja README.")
        grp_help.add(row_goodix)

        row_keys = Adw.ActionRow.new()
        row_keys.set_title("Atalhos")
        row_keys.set_subtitle("Ctrl+R recarregar, Ctrl+Q sair")
        grp_help.add(row_keys)

    def _bind_keys(self):
        ctl = Gtk.ShortcutController.new()
        ctl.set_scope(Gtk.ShortcutScope.GLOBAL)
        ctl.add_shortcut(
            Gtk.Shortcut.new(
                Gtk.KeyvalTrigger.new(ord("r"), Gdk.ModifierType.CONTROL_MASK),
                Gtk.CallbackAction.new(lambda *_: (self.refresh_all(), True)[1]),
            )
        )
        ctl.add_shortcut(
            Gtk.Shortcut.new(
                Gtk.KeyvalTrigger.new(ord("q"), Gdk.ModifierType.CONTROL_MASK),
                Gtk.CallbackAction.new(lambda *_: (self.app.quit(), True)[1]),
            )
        )
        self.add_controller(ctl)

    # -- dados -------------------------------------------------------
    def toast(self, msg: str):
        try:
            self.toast_overlay.add_toast(Adw.Toast.new(msg))
        except Exception:
            pass

    def refresh_all(self):
        if self._loading:
            return
        self._loading = True
        device_cfg = self.settings.get_string("device-path")

        def _load():
            devices = fprintd.get_devices()
            dev = fprintd.resolve_device(device_cfg)
            props = fprintd.get_device_props(dev) if dev else {}
            enrolled: list[str] = []
            if dev:
                enrolled = fprintd.list_enrolled_fingers(fprintd.current_user(), dev)
            pam_ok, pam_text = pam.current_profile_text()
            pam_on = pam.is_enabled() if pam_ok else False
            return {
                "devices": devices,
                "dev": dev,
                "props": props,
                "enrolled": enrolled,
                "pam_on": pam_on,
                "pam_text": pam_text if pam_ok else pam_text,
            }

        def _done(res):
            self._loading = False
            if isinstance(res, Exception):
                self.toast(f"Falha ao recarregar: {res}")
                return False
            self._devices = res["devices"]
            self._device_path = res["dev"]
            self._props = res["props"]
            self._enrolled = res["enrolled"]
            self._pam_enabled = res["pam_on"]
            self._pam_text = res["pam_text"]
            self._render_all()
            return False

        run_in_thread(_load, _done)

    def _render_all(self):
        has_reader = bool(self._device_path)
        # Banner persistente (spec 6.1.2): sem-leitor > sem-watcher
        if not has_reader:
            self.banner.set_title("Nenhum leitor encontrado. Verifique drivers.")
            self.banner.set_revealed(True)
        elif self.tray is not None and not self.tray.has_watcher():
            self.banner.set_title(
                "Tray indisponível neste GNOME — o app funciona como janela."
            )
            self.banner.set_revealed(True)
        else:
            self.banner.set_revealed(False)

        # device combo (sem disparar reload em cascata)
        self._block_device_signal = True
        try:
            self.device_model.splice(0, self.device_model.get_n_items(), [])
            self.device_model.append("auto (padrão)")
            for d in self._devices:
                try:
                    label = fprintd.get_device_props(d).get("name", d)
                except Exception:
                    label = d
                self.device_model.append(f"{label}  [{d}]")
            if self._device_path and self._device_path in self._devices:
                idx = self._devices.index(self._device_path) + 1
                self.combo_device.set_selected(
                    min(idx, self.device_model.get_n_items() - 1)
                )
            else:
                self.combo_device.set_selected(0)
        finally:
            self._block_device_signal = False

        name = self._props.get("name", "—")
        stype = self._props.get("scan-type", "—")
        stages = self._props.get("num-enroll-stages", "—")
        present = self._props.get("finger-present", False)
        self.row_model.set_subtitle(str(name))
        self.row_type.set_subtitle(f"{stype} ({'deslize' if stype == 'swipe' else 'encoste'})")
        self.row_stages.set_subtitle(str(stages))
        self.row_present.set_subtitle("sim" if present else "não")
        self.status_no_device.set_visible(not has_reader)
        self._grp_nodev_wrap.set_visible(not has_reader)
        self.grp_reader.set_visible(has_reader)

        # dedos
        while (row := self.finger_rows_box.get_first_child()) is not None:
            self.finger_rows_box.remove(row)
        for fid in self._enrolled:
            r = Adw.ActionRow.new()
            r.set_title(fprintd.finger_label(fid))
            r.set_subtitle(fid)
            r.add_prefix(Gtk.Image.new_from_icon_name("fingerprint-symbolic"))
            b = Gtk.Button.new_from_icon_name("user-trash-symbolic")
            b.set_tooltip_text(f"Apagar {fid}")
            b.add_css_class("flat")
            b.connect("clicked", self._on_delete_one, fid)
            r.add_suffix(b)
            self.finger_rows_box.append(r)
        self.grp_fingers.set_title(f"{len(self._enrolled)} de 10 dedos cadastrados")
        empty = len(self._enrolled) == 0
        self.status_no_fingers.set_visible(empty)
        self._grp_nof_wrap.set_visible(empty)
        self.finger_rows_box.set_visible(not empty)

        can_bio = has_reader
        self.btn_enroll.set_sensitive(can_bio)
        self.btn_verify.set_sensitive(can_bio and len(self._enrolled) > 0)
        self.btn_delete_all.set_sensitive(len(self._enrolled) > 0)
        if not can_bio:
            self.btn_enroll.set_tooltip_text("Sem leitor — conecte um leitor primeiro")
        elif not self.btn_verify.is_sensitive():
            self.btn_verify.set_tooltip_text("Cadastre ao menos uma digital primeiro")

        # PAM
        self._block_pam_signal = True
        try:
            self.switch_pam.set_active(self._pam_enabled)
            if not pam.has_authselect():
                self.switch_pam.set_sensitive(False)
                self.switch_pam.set_subtitle("authselect não encontrado")
            else:
                self.switch_pam.set_sensitive(True)
                self.switch_pam.set_subtitle(
                    "Ativado (with-fingerprint)" if self._pam_enabled else "Desativado"
                )
        finally:
            self._block_pam_signal = False
        self.row_pam_detail.set_subtitle(
            (self._pam_text[:160] + "…") if len(self._pam_text) > 160 else self._pam_text
        )

        self._update_host_row()
        if self.tray is not None:
            self.tray.update(
                enrolled_count=len(self._enrolled),
                pam_enabled=self._pam_enabled,
                device_name=str(name) if has_reader else "",
            )

    # -- device ------------------------------------------------------
    def _on_device_changed(self, combo, _pspec):
        if self._block_device_signal:
            return
        sel = combo.get_selected()
        if sel == 0:
            self.settings.set_string("device-path", "auto")
        elif 1 <= sel <= len(self._devices):
            self.settings.set_string("device-path", self._devices[sel - 1])
        else:
            return
        self.refresh_all()

    # -- dedos -------------------------------------------------------
    def _finger_chooser_dialog(self, on_pick):
        dlg = Adw.AlertDialog.new("Cadastrar qual dedo?", None)
        opts = [
            ("right-index-finger", "Indicador direito"),
            ("left-index-finger", "Indicador esquerdo"),
            ("right-thumb", "Polegar direito"),
            ("left-thumb", "Polegar esquerdo"),
        ]
        for fid, label in opts:
            dlg.add_response(fid, label)
        dlg.add_response("cancel", "Cancelar")
        dlg.set_default_response("right-index-finger")
        dlg.choose(self, None, lambda d, r, _: on_pick(d.choose_finish(r)), None)

    def open_enroll_chooser(self):
        self._finger_chooser_dialog(self._on_finger_picked)

    def _on_finger_picked(self, fid: str):
        if fid == "cancel":
            return
        stages = int(self._props.get("num-enroll-stages", 5) or 5)
        stype = self._props.get("scan-type", "press")
        instr = (
            "Deslize o dedo da ponta à base, "
            f"{stages} vezes."
            if stype == "swipe"
            else f"Encoste e retire o dedo {stages} vezes."
        )
        win = EnrollWindow(
            self,
            f"Cadastrar — {fprintd.finger_label(fid)}",
            fprintd.enroll_cmd(fid),
            stages=stages,
            instruction=instr,
            on_done=lambda ok: (self.toast("Digital cadastrada"), self.refresh_all())
            if ok
            else self.refresh_all(),
        )
        win.present()

    def open_verify(self):
        win = EnrollWindow(
            self,
            "Verificar digital",
            fprintd.verify_cmd(),
            stages=1,
            instruction="Encoste o dedo cadastrado no leitor.",
            on_done=lambda ok: self.toast("Verificação OK" if ok else "Verificação falhou"),
        )
        win.present()

    def _on_delete_one(self, _btn, fid: str):
        dlg = Adw.AlertDialog.new(f"Apagar {fprintd.finger_label(fid)}?", None)
        dlg.add_response("cancel", "Cancelar")
        dlg.add_response("delete", "Apagar")
        dlg.set_response_appearance("delete", Adw.ResponseAppearance.DESTRUCTIVE)
        dlg.choose(self, None, lambda d, r, _: self._do_delete_one(fid, d.choose_finish(r)), None)

    def _do_delete_one(self, fid: str, resp: str):
        if resp != "delete":
            return

        def _load():
            user = fprintd.current_user()
            return subprocess.run(
                fprintd.delete_cmd(user, fid), capture_output=True, text=True, timeout=30
            )

        def _done(res):
            if isinstance(res, Exception) or res.returncode != 0:
                self.toast("Falha ao apagar.")
            else:
                self.toast("Digital apagada.")
            self.refresh_all()
            return False

        run_in_thread(_load, _done)

    def confirm_delete_all(self):
        dlg = Adw.AlertDialog.new("Apagar todas as digitais?", "Isso remove todas do usuário atual.")
        dlg.add_response("cancel", "Cancelar")
        dlg.add_response("delete", "Apagar todas")
        dlg.set_response_appearance("delete", Adw.ResponseAppearance.DESTRUCTIVE)
        dlg.choose(self, None, lambda d, r, _: self._do_delete_all(d.choose_finish(r)), None)

    def _do_delete_all(self, resp: str):
        if resp != "delete":
            return

        def _load():
            user = fprintd.current_user()
            return subprocess.run(
                fprintd.delete_cmd(user), capture_output=True, text=True, timeout=30
            )

        def _done(res):
            self.toast("Todas apagadas." if not isinstance(res, Exception) and res.returncode == 0 else "Falha ao apagar.")
            self.refresh_all()
            return False

        run_in_thread(_load, _done)

    # -- PAM ---------------------------------------------------------
    def _on_pam_toggled(self, row, _pspec):
        if self._block_pam_signal:
            return
        enable = row.get_active()
        row.set_sensitive(False)
        row.set_subtitle("Aplicando... (polkit vai pedir senha)")

        def _load():
            return pam.set_enabled(enable)

        def _done(res):
            row.set_sensitive(True)
            if isinstance(res, Exception):
                ok, out = False, str(res)
            else:
                ok, out = res
            if not ok:
                # reverte visual
                self._block_pam_signal = True
                try:
                    row.set_active(not enable)
                finally:
                    self._block_pam_signal = False
                self.toast("Autenticação cancelada" if "polkit" in out.lower() or not out else f"Falha: {out[:120]}")
            else:
                self.toast("PAM atualizado.")
            self.refresh_all()
            return False

        run_in_thread(_load, _done)

    # -- tray page ---------------------------------------------------
    def _on_tray_toggled(self, row, _pspec):
        active = row.get_active()
        self.settings.set_boolean("show-tray", active)
        if self.tray is None:
            return
        if active:
            self.tray.start()
            self.toast("Tray ativado.")
        else:
            self.tray.stop()
            self.toast("Tray desativado (app segue aberto).")
        self._update_host_row()

    def _update_host_row(self):
        if self.tray is not None and self.tray.has_watcher():
            self.row_host.set_subtitle("Ativo — ícone visível")
        else:
            self.row_host.set_subtitle("Ausente — app segue como janela")

    def _on_autostart_toggled(self, row, _pspec):
        try:
            if row.get_active():
                os.makedirs(os.path.dirname(AUTOSTART_PATH), exist_ok=True)
                with open(AUTOSTART_PATH, "w", encoding="utf-8") as f:
                    f.write(
                        "[Desktop Entry]\nType=Application\n"
                        "Name=Fingerprint Manager\n"
                        "Exec=fingerprint-manager --background\n"
                        "Icon=fingerprint-symbolic\n"
                        "X-GNOME-Autostart-enabled=true\n"
                    )
                self.toast("Autostart ativado.")
            else:
                if os.path.exists(AUTOSTART_PATH):
                    os.remove(AUTOSTART_PATH)
                self.toast("Autostart desativado.")
        except Exception as e:
            self.toast(f"Falha no autostart: {e}")

    def _start_auto_refresh(self):
        interval = max(5, min(120, self.settings.get_int("refresh")))

        def _tick():
            if not self._loading:
                self.refresh_all()
            return True

        GLib.timeout_add_seconds(interval, _tick)

    # -- ações header/ajuda ------------------------------------------
    def _act_open_settings(self, _act, _param):
        try:
            subprocess.Popen(["gnome-control-center", "user-accounts"])
        except Exception as e:
            self.toast(f"Falha ao abrir Ajustes: {e}")

    def _act_copy_logs(self, _act, _param):
        self._copy_text(self._logs_text())

    def _act_about(self, _act, _param):
        dlg = Adw.AboutDialog.new()
        dlg.set_application_name("Fingerprint Manager")
        dlg.set_version("0.1.0")
        dlg.set_comments("Gerencie digitais e desbloqueio por impressão digital.")
        dlg.set_website("https://github.com/anomalyco/opencode")
        dlg.present(self)

    def _logs_text(self) -> str:
        try:
            p = subprocess.run(
                ["journalctl", "--user", "-n", "200", "--no-pager"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return p.stdout[-4000:] or "(sem logs)"
        except Exception as e:
            return f"(falha ao ler logs: {e})"

    def _diag_text(self) -> str:
        parts = []
        try:
            p = subprocess.run(
                ["busctl", "--session", "list"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            parts.append(
                "\n".join(l for l in p.stdout.splitlines() if "tatus" in l)
                or "(sem watcher SNI)"
            )
        except Exception as e:
            parts.append(f"busctl falhou: {e}")
        try:
            p = subprocess.run(
                ["fprintd-list", fprintd.current_user()],
                capture_output=True,
                text=True,
                timeout=10,
            )
            parts.append(p.stdout + p.stderr)
        except Exception as e:
            parts.append(f"fprintd-list falhou: {e}")
        return "\n---\n".join(parts)

    def _copy_text(self, text: str):
        try:
            display = Gdk.Display.get_default()
            if display:
                display.get_clipboard().set(text)
                self.toast("Copiado.")
                return
        except Exception:
            pass
        self.toast("Falha ao copiar.")
