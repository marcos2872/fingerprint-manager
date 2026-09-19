"""backend/fprintd.py com D-Bus mockado.

Crítico: todo call_sync precisa de timeout finito (o freeze foi timeout -1
na thread GTK) e resolve_device não pode buscar GetDevices duas vezes.
"""

from gi.repository import GLib

from backend import fprintd


class FakeResult:
    def __init__(self, *values):
        self._values = values

    def unpack(self):
        return self._values


class FakeProxy:
    """Responde GetDevices/GetDefaultDevice/Get/ListEnrolledFingers."""

    def __init__(self, calls, devices=None, default=None, props=None, enrolled=None, error=None):
        self.calls = calls
        self.devices = devices or []
        self.default = default
        self.props = props or {}
        self.enrolled = enrolled or []
        self.error = error

    def call_sync(self, method, *args):
        # args: (params, flags, timeout, cancellable)
        timeout = args[2] if len(args) > 2 else None
        self.calls.append((method, timeout))
        assert timeout is not None and timeout != -1, "call_sync sem timeout finito!"
        if self.error and method == self.error[0]:
            raise self.error[1]
        if method == "GetDevices":
            return FakeResult(self.devices)
        if method == "GetDefaultDevice":
            return FakeResult(self.default or "/")
        if method == "Get":
            key = args[0].unpack()[1]
            if key not in self.props:
                # fprintd real levanta; o código mantém o default
                raise Exception(f"UnknownProperty: {key}")
            val = self.props[key]
            if isinstance(val, bool):
                inner = GLib.Variant("b", val)
            elif isinstance(val, int):
                inner = GLib.Variant("i", val)
            else:
                inner = GLib.Variant("s", str(val))
            return FakeResult(GLib.Variant.new_variant(inner))
        if method == "ListEnrolledFingers":
            return FakeResult(self.enrolled)
        raise AssertionError(f"método inesperado: {method}")


def _patch_manager(monkeypatch, **kw):
    calls = []
    proxy = FakeProxy(calls, **kw)
    monkeypatch.setattr(fprintd, "_manager_proxy", lambda: proxy)
    return proxy, calls


def _patch_bus(monkeypatch, **kw):
    """Para get_device_props/list_enrolled (criam Gio.DBusProxy direto)."""
    calls = []
    proxy = FakeProxy(calls, **kw)
    import gi.repository.Gio as Gio

    monkeypatch.setattr(
        Gio.DBusProxy, "new_for_bus_sync", staticmethod(lambda *a, **k: proxy)
    )
    return proxy, calls


def test_get_devices_ok(monkeypatch):
    _, calls = _patch_manager(monkeypatch, devices=["/dev/0", "/dev/1"])
    assert fprintd.get_devices() == ["/dev/0", "/dev/1"]
    assert calls[0][1] == fprintd.DBUS_TIMEOUT_MS


def test_get_devices_erro_vira_lista_vazia(monkeypatch):
    def boom():
        raise Exception("sem bus")

    monkeypatch.setattr(fprintd, "_manager_proxy", boom)
    assert fprintd.get_devices() == []


def test_resolve_com_lista_nao_busca_de_novo(monkeypatch):
    """_load() passa a lista: resolve NÃO pode chamar GetDevices outra vez."""
    calls = []
    monkeypatch.setattr(
        fprintd, "get_devices", lambda: calls.append("devices") or ["/a", "/b"]
    )
    monkeypatch.setattr(fprintd, "get_default_device", lambda: "/b")
    assert fprintd.resolve_device("auto", ["/a", "/b"]) == "/b"
    assert calls == []


def test_resolve_sem_lista_busca_uma_vez(monkeypatch):
    calls = []
    monkeypatch.setattr(
        fprintd, "get_devices", lambda: calls.append(1) or ["/a", "/b"]
    )
    monkeypatch.setattr(fprintd, "get_default_device", lambda: "/")
    assert fprintd.resolve_device("auto") == "/a"
    assert len(calls) == 1


def test_resolve_configurado_inexistente_cai_no_primeiro():
    assert fprintd.resolve_device("/x", ["/a", "/b"]) == "/a"
    assert fprintd.resolve_device("auto", []) is None


def test_props_com_defaults(monkeypatch):
    _, calls = _patch_bus(
        monkeypatch, props={"name": "Validity", "scan-type": "swipe"}
    )
    props = fprintd.get_device_props("/dev/0")
    assert props["name"] == "Validity"
    assert props["scan-type"] == "swipe"
    assert props["num-enroll-stages"] == 5  # default
    assert props["finger-present"] is False  # default
    assert all(t == fprintd.DBUS_TIMEOUT_MS for _, t in calls)


def test_list_enrolled_ok(monkeypatch):
    _patch_bus(monkeypatch, enrolled=["right-index-finger"])
    assert fprintd.list_enrolled_fingers("u", "/dev/0") == ["right-index-finger"]


def test_no_enrolled_prints_vira_lista_vazia(monkeypatch):
    _patch_bus(
        monkeypatch,
        error=("ListEnrolledFingers", Exception("GDBus NoEnrolledPrints")),
    )
    assert fprintd.list_enrolled_fingers("u", "/dev/0") == []


def test_labels_e_cmds():
    assert fprintd.finger_label("right-index-finger") == "Indicador direito"
    assert fprintd.finger_label("xx") == "xx"
    assert fprintd.enroll_cmd("left-thumb") == ["fprintd-enroll", "-f", "left-thumb"]
    assert fprintd.verify_cmd() == ["fprintd-verify"]
