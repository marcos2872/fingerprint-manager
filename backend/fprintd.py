"""Backend genérico para fprintd via system bus.

Nada hardcoded por modelo. Tudo via net.reactivated.Fprint.
"""

from __future__ import annotations

import getpass

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib  # noqa: E402

BUS_NAME = "net.reactivated.Fprint"
MANAGER_PATH = "/net/reactivated/Fprint/Manager"
MANAGER_IFACE = "net.reactivated.Fprint.Manager"
DEVICE_IFACE = "net.reactivated.Fprint.Device"
PROPS_IFACE = "org.freedesktop.DBus.Properties"

# Timeout finito para todo call_sync. Motivo: -1 = infinito congela a
# thread chamadora; quando chamado na thread GTK (render), congela o
# GNOME inteiro. 5s é suficiente para fprintd local responder.
DBUS_TIMEOUT_MS = 5000

FINGERS = [
    "left-thumb",
    "left-index-finger",
    "left-middle-finger",
    "left-ring-finger",
    "left-little-finger",
    "right-thumb",
    "right-index-finger",
    "right-middle-finger",
    "right-ring-finger",
    "right-little-finger",
]

FINGER_LABELS_PT = {
    "left-thumb": "Polegar esquerdo",
    "left-index-finger": "Indicador esquerdo",
    "left-middle-finger": "Médio esquerdo",
    "left-ring-finger": "Anelar esquerdo",
    "left-little-finger": "Mínimo esquerdo",
    "right-thumb": "Polegar direito",
    "right-index-finger": "Indicador direito",
    "right-middle-finger": "Médio direito",
    "right-ring-finger": "Anelar direito",
    "right-little-finger": "Mínimo direito",
}


def finger_label(finger_id: str) -> str:
    return FINGER_LABELS_PT.get(finger_id, finger_id)


def current_user() -> str:
    return getpass.getuser()


def _manager_proxy() -> Gio.DBusProxy:
    return Gio.DBusProxy.new_for_bus_sync(
        Gio.BusType.SYSTEM,
        Gio.DBusProxyFlags.NONE,
        None,
        BUS_NAME,
        MANAGER_PATH,
        MANAGER_IFACE,
        None,
    )


def get_devices() -> list[str]:
    """Retorna object paths. Lista vazia = sem leitor (não é erro)."""
    try:
        proxy = _manager_proxy()
        result = proxy.call_sync(
            "GetDevices", None, Gio.DBusCallFlags.NONE, DBUS_TIMEOUT_MS, None
        )
        return list(result.unpack()[0])
    except Exception:
        return []


def get_default_device() -> str | None:
    try:
        proxy = _manager_proxy()
        result = proxy.call_sync(
            "GetDefaultDevice", None, Gio.DBusCallFlags.NONE, DBUS_TIMEOUT_MS, None
        )
        path = result.unpack()[0]
        return path if path and path != "/" else None
    except Exception:
        return None


def resolve_device(configured: str = "auto", devices: list[str] | None = None) -> str | None:
    """'auto' -> default ou primeiro. Senão retorna o configurado se existir."""
    if devices is None:
        devices = get_devices()
    if not devices:
        return None
    if configured and configured != "auto":
        return configured if configured in devices else devices[0]
    default = get_default_device()
    if default and default in devices:
        return default
    return devices[0]


def get_device_props(device_path: str) -> dict:
    """Props genéricas: name, scan-type, num-enroll-stages, finger-present."""
    props = {
        "name": "Desconhecido",
        "scan-type": "press",
        "num-enroll-stages": 5,
        "finger-present": False,
    }
    try:
        proxy = Gio.DBusProxy.new_for_bus_sync(
            Gio.BusType.SYSTEM,
            Gio.DBusProxyFlags.NONE,
            None,
            BUS_NAME,
            device_path,
            PROPS_IFACE,
            None,
        )
        for key, _default in list(props.items()):
            try:
                res = proxy.call_sync(
                    "Get",
                    GLib.Variant("(ss)", (DEVICE_IFACE, key)),
                    Gio.DBusCallFlags.NONE,
                    DBUS_TIMEOUT_MS,
                    None,
                )
                val = res.unpack()[0]
                # Get retorna (v): desempacota o Variant interno
                if hasattr(val, "unpack"):
                    try:
                        val = val.unpack()
                    except Exception:
                        pass
                props[key] = val
            except Exception:
                continue
    except Exception:
        pass
    return props


def list_enrolled_fingers(username: str, device_path: str) -> list[str]:
    """Lista dedos cadastrados. NoEnrolledPrints -> [] (não falha)."""
    try:
        proxy = Gio.DBusProxy.new_for_bus_sync(
            Gio.BusType.SYSTEM,
            Gio.DBusProxyFlags.NONE,
            None,
            BUS_NAME,
            device_path,
            DEVICE_IFACE,
            None,
        )
        result = proxy.call_sync(
            "ListEnrolledFingers",
            GLib.Variant("(s)", (username,)),
            Gio.DBusCallFlags.NONE,
            DBUS_TIMEOUT_MS,
            None,
        )
        return list(result.unpack()[0])
    except Exception as e:
        # fprintd retorna NoEnrolledPrints quando zero digitais
        if "NoEnrolledPrints" in str(e):
            return []
        return []


# --- Comandos delegados (não reimplementar Claim/Enroll) ---


def enroll_cmd(finger: str) -> list[str]:
    return ["fprintd-enroll", "-f", finger]


def verify_cmd() -> list[str]:
    return ["fprintd-verify"]


def list_cmd(username: str) -> list[str]:
    return ["fprintd-list", username]


def delete_cmd(username: str, finger: str | None = None) -> list[str]:
    if finger:
        return ["fprintd-delete", "-f", finger, username]
    return ["fprintd-delete", username]
