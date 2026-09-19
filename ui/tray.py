"""Tray StatusNotifierItem puro-D-Bus (sem GTK3/AppIndicator).

- Registra org.kde.StatusNotifierItem no session bus.
- Se não houver watcher (GNOME 48-50 padrão), registra mas não aparece.
  App segue 100% como janela. Por isso é opcional/desligável.
- Menu via com.canonical.dbusmenu mínimo (lista fixa da spec 6.1.9).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib  # noqa: E402

SNI_IFACE_XML = """
<node>
  <interface name="org.kde.StatusNotifierItem">
    <method name="ContextMenu"><arg type="i" direction="in"/><arg type="i" direction="in"/></method>
    <method name="Activate"><arg type="i" direction="in"/><arg type="i" direction="in"/></method>
    <method name="SecondaryActivate"><arg type="i" direction="in"/><arg type="i" direction="in"/></method>
    <method name="Scroll"><arg type="i" direction="in"/><arg type="s" direction="in"/></method>
    <signal name="NewTitle"/>
    <signal name="NewIcon"/>
    <signal name="NewStatus"><arg type="s"/></signal>
    <signal name="NewToolTip"/>
    <property name="Category" type="s" access="read"/>
    <property name="Id" type="s" access="read"/>
    <property name="Title" type="s" access="read"/>
    <property name="Status" type="s" access="read"/>
    <property name="WindowId" type="i" access="read"/>
    <property name="IconName" type="s" access="read"/>
    <property name="ToolTip" type="(sa(iiay)ss)" access="read"/>
    <property name="Menu" type="o" access="read"/>
    <property name="ItemIsMenu" type="b" access="read"/>
  </interface>
</node>
"""

DBUSMENU_IFACE_XML = """
<node>
  <interface name="com.canonical.dbusmenu">
    <method name="GetLayout">
      <arg type="i" direction="in"/><arg type="i" direction="in"/><arg type="as" direction="in"/>
      <arg type="u" direction="out"/><arg type="(ia{sv}av)" direction="out"/>
    </method>
    <method name="GetGroupProperties">
      <arg type="ai" direction="in"/><arg type="as" direction="in"/>
      <arg type="a(ia{sv})" direction="out"/>
    </method>
    <method name="GetProperty">
      <arg type="i" direction="in"/><arg type="s" direction="in"/>
      <arg type="v" direction="out"/>
    </method>
    <method name="Event">
      <arg type="i" direction="in"/><arg type="s" direction="in"/><arg type="v" direction="in"/><arg type="u" direction="in"/>
    </method>
    <method name="EventGroup">
      <arg type="a(iisvu)" direction="in"/>
    </method>
    <method name="AboutToShow"><arg type="i" direction="in"/><arg type="b" direction="out"/></method>
    <signal name="LayoutUpdated"><arg type="u"/><arg type="i"/></signal>
    <signal name="ItemsPropertiesUpdated"><arg type="a(ia{sv})"/><arg type="a(ia{sv})"/></signal>
  </interface>
</node>
"""


@dataclass
class TrayState:
    enrolled_count: int = 0
    pam_enabled: bool = False
    device_name: str = ""
    pam_toggle_visible: bool = True


class StatusNotifierTray:
    """API usada pela janela: start/stop/update/callbacks."""

    def __init__(self):
        self._conn: Gio.DBusConnection | None = None
        self._bus_name: str | None = None
        self._reg_id = 0
        self._sni_id = 0
        self._menu_id = 0
        self._running = False
        self.state = TrayState()
        # callbacks configurados pela window
        self.on_open = lambda: None
        self.on_enroll = lambda: None
        self.on_verify = lambda: None
        self.on_pam_toggle = lambda: None
        self.on_quit = lambda: None

        # ids fixos do menu (spec 6.1.9)
        self._IDS = {
            "state": 0,
            "open": 1,
            "enroll": 2,
            "verify": 3,
            "pam": 4,
            "quit": 5,
        }

    # -- estado -----------------------------------------------------
    @property
    def running(self) -> bool:
        return self._running

    def tooltip(self) -> str:
        pam = "on" if self.state.pam_enabled else "off"
        dev = self.state.device_name or "sem leitor"
        return f"Fingerprint: {self.state.enrolled_count} digitais, PAM {pam}, {dev}"

    def has_watcher(self) -> bool:
        try:
            conn = Gio.bus_get_sync(Gio.BusType.SESSION, None)
            res = conn.call_sync(
                "org.kde.StatusNotifierWatcher",
                "/StatusNotifierWatcher",
                "org.freedesktop.DBus.Properties",
                "Get",
                GLib.Variant(
                    "(ss)",
                    ("org.kde.StatusNotifierWatcher", "RegisteredStatusNotifierItems"),
                ),
                Gio.DBusCallFlags.NONE,
                -1,
                None,
            )
            return True if res else True
        except Exception:
            # fallback: nome no bus?
            try:
                conn = Gio.bus_get_sync(Gio.BusType.SESSION, None)
                res = conn.call_sync(
                    "org.freedesktop.DBus",
                    "/org/freedesktop/DBus",
                    "org.freedesktop.DBus",
                    "NameHasOwner",
                    GLib.Variant("(s,)", ("org.kde.StatusNotifierWatcher",)),
                    Gio.DBusCallFlags.NONE,
                    -1,
                    None,
                )
                return bool(res.unpack()[0])
            except Exception:
                return False

    # -- ciclo de vida ----------------------------------------------
    def start(self) -> bool:
        if self._running:
            return True
        try:
            self._conn = Gio.bus_get_sync(Gio.BusType.SESSION, None)
            sni_node = Gio.DBusNodeInfo.new_for_xml(SNI_IFACE_XML)
            menu_node = Gio.DBusNodeInfo.new_for_xml(DBUSMENU_IFACE_XML)

            self._sni_id = self._conn.register_object(
                "/StatusNotifierItem",
                sni_node.interfaces[0],
                self._handle_sni,
                None,
                None,
            )
            self._menu_id = self._conn.register_object(
                "/Menu",
                menu_node.interfaces[0],
                self._handle_menu,
                None,
                None,
            )
            # nome único; watcher registra por este nome
            flags = Gio.BusNameOwnerFlags.ALLOW_REPLACEMENT | Gio.BusNameOwnerFlags.REPLACE
            self._reg_id = Gio.bus_own_name(
                Gio.BusType.SESSION,
                "org.kde.StatusNotifierItem-fingerprint-manager",
                flags,
                None,
                None,
                None,
                None,
            )
            self._register_with_watcher()
            self._running = True
            return True
        except Exception:
            self.stop()
            return False

    def stop(self):
        try:
            if self._conn:
                if self._sni_id:
                    self._conn.unregister_object(self._sni_id)
                if self._menu_id:
                    self._conn.unregister_object(self._menu_id)
        except Exception:
            pass
        self._sni_id = 0
        self._menu_id = 0
        self._conn = None
        self._running = False

    def _register_with_watcher(self):
        if not self._conn:
            return
        try:
            self._conn.call(
                "org.kde.StatusNotifierWatcher",
                "/StatusNotifierWatcher",
                "org.kde.StatusNotifierWatcher",
                "RegisterStatusNotifierItem",
                GLib.Variant("(s,)", ("org.kde.StatusNotifierItem-fingerprint-manager",)),
                Gio.DBusCallFlags.NONE,
                -1,
                None,
                None,
                None,
            )
        except Exception:
            pass  # sem watcher: registra mas não aparece (esperado no GNOME)

    def update(self, enrolled_count=None, pam_enabled=None, device_name=None):
        if enrolled_count is not None:
            self.state.enrolled_count = enrolled_count
        if pam_enabled is not None:
            self.state.pam_enabled = pam_enabled
        if device_name is not None:
            self.state.device_name = device_name
        self._emit_layout_updated()

    def _emit_layout_updated(self):
        if not self._conn or not self._running:
            return
        try:
            self._conn.emit_signal(
                None,
                "/Menu",
                "com.canonical.dbusmenu",
                "LayoutUpdated",
                GLib.Variant("(ui)", (0, 0)),
            )
        except Exception:
            pass

    # -- D-Bus: SNI --------------------------------------------------
    def _handle_sni(self, conn, sender, path, iface, method, params, invocation):
        try:
            if method in ("Activate", "ContextMenu"):
                GLib.idle_add(self.on_open)
                invocation.return_value(None)
            elif method == "SecondaryActivate":
                GLib.idle_add(self.on_verify)
                invocation.return_value(None)
            elif method == "Scroll":
                invocation.return_value(None)
            else:
                invocation.return_value(None)
        except Exception:
            try:
                invocation.return_value(None)
            except Exception:
                pass

    def _sni_get_property(self, name: str) -> GLib.Variant:
        if name == "Category":
            return GLib.Variant("s", "Hardware")
        if name == "Id":
            return GLib.Variant("s", "fingerprint-manager")
        if name == "Title":
            return GLib.Variant("s", "Fingerprint Manager")
        if name == "Status":
            return GLib.Variant("s", "Active")
        if name == "WindowId":
            return GLib.Variant("i", 0)
        if name == "IconName":
            return GLib.Variant("s", "fingerprint-symbolic")
        if name == "ToolTip":
            return GLib.Variant(
                "(sa(iiay)ss)", ("", [], self.tooltip(), "")
            )
        if name == "Menu":
            return GLib.Variant("o", "/Menu")
        if name == "ItemIsMenu":
            return GLib.Variant("b", False)
        return GLib.Variant("s", "")

    # -- D-Bus: dbusmenu ---------------------------------------------
    def _menu_items(self):
        pam_label = (
            "Desativar PAM (digital)"
            if self.state.pam_enabled
            else "Ativar PAM (digital)"
        )
        state_label = (
            f"Estado: {self.state.enrolled_count} digitais, "
            f"PAM {'on' if self.state.pam_enabled else 'off'}"
        )
        I = self._IDS
        return [
            (I["state"], state_label, False),
            (I["open"], "Abrir gerenciador", True),
            (I["enroll"], "Cadastrar...", True),
            (I["verify"], "Verificar...", True),
            (I["pam"], pam_label, True),
            (I["quit"], "Sair", True),
        ]

    def _layout_variant(self):
        items = []
        for vid, label, enabled in self._menu_items():
            props = {
                "label": GLib.Variant("s", label),
                "enabled": GLib.Variant("b", enabled),
                "visible": GLib.Variant("b", True),
            }
            items.append(GLib.Variant("(ia{sv}av)", (vid, props, [])))
        root_props = {
            "label": GLib.Variant("s", "root"),
            "children-display": GLib.Variant("s", "submenu"),
        }
        root = GLib.Variant("(ia{sv}av)", (0, root_props, items))
        return GLib.Variant("(u(ia{sv}av))", (0, root))

    def _handle_menu(self, conn, sender, path, iface, method, params, invocation):
        try:
            if method == "GetLayout":
                invocation.return_value(self._layout_variant())
            elif method == "GetGroupProperties":
                ids, _props = params.unpack()
                out = []
                labels = {vid: lab for vid, lab, _en in self._menu_items()}
                enabled = {vid: en for vid, _lab, en in self._menu_items()}
                for vid in ids:
                    out.append(
                        (
                            vid,
                            {
                                "label": GLib.Variant("s", labels.get(vid, "")),
                                "enabled": GLib.Variant("b", enabled.get(vid, True)),
                                "visible": GLib.Variant("b", True),
                            },
                        )
                    )
                invocation.return_value(GLib.Variant("(a(ia{sv}))", (out,)))
            elif method == "GetProperty":
                vid, name = params.unpack()
                labels = {v: lab for v, lab, _ in self._menu_items()}
                if name == "label":
                    invocation.return_value(
                        GLib.Variant("(v)", (GLib.Variant("s", labels.get(vid, "")),))
                    )
                elif name == "enabled":
                    invocation.return_value(
                        GLib.Variant("(v)", (GLib.Variant("b", True),))
                    )
                else:
                    invocation.return_value(
                        GLib.Variant("(v)", (GLib.Variant("s", ""),))
                    )
            elif method == "Event":
                vid, event, _data, _ts = params.unpack()
                if event in ("clicked", "activated"):
                    self._dispatch(vid)
                invocation.return_value(None)
            elif method == "EventGroup":
                for vid, event, _d, _t in params.unpack()[0]:
                    if event in ("clicked", "activated"):
                        self._dispatch(vid)
                invocation.return_value(None)
            elif method == "AboutToShow":
                invocation.return_value(GLib.Variant("(b)", (False,)))
            else:
                invocation.return_value(None)
        except Exception:
            try:
                invocation.return_value(None)
            except Exception:
                pass

    def _dispatch(self, vid: int):
        I = self._IDS
        if vid == I["open"]:
            GLib.idle_add(self.on_open)
        elif vid == I["enroll"]:
            GLib.idle_add(self.on_enroll)
        elif vid == I["verify"]:
            GLib.idle_add(self.on_verify)
        elif vid == I["pam"]:
            GLib.idle_add(self.on_pam_toggle)
        elif vid == I["quit"]:
            GLib.idle_add(self.on_quit)
        # state (0) é informativo: ignora
