# Fingerprint Manager

App GTK4/Adwaita para gerenciar **cadastro de digitais e desbloqueio por biometria**
no Fedora/GNOME — sem extensão do GNOME Shell, sem congelar a top bar.

- Janela real com 5 páginas: **Dispositivo · Digitais · Desbloqueio · Tray · Ajuda**
- Cadastro/verificação via `fprintd-enroll` / `fprintd-verify` em terminal **Vte embutido**
- Liga/desliga `with-fingerprint` via **authselect + pkexec** (nunca edita `/etc/pam.d` na mão)
- **Tray próprio** StatusNotifierItem puro-D-Bus, **desativável** — sem host SNI
  (GNOME 48–50 padrão) o app funciona 100% como janela
- Genérico: qualquer leitor do `net.reactivated.Fprint` (Validity, Goodix, Synaptics, ELAN…)

Detalhes de arquitetura e UI/UX normativa: ver [`PLANO.md`](PLANO.md).

## Requisitos (Fedora)

```bash
sudo dnf install python3 python3-gobject gtk4 libadwaita vte291-gtk4 \
  fprintd authselect polkit gnome-control-center
# opcional, só para o ícone do tray aparecer no GNOME:
sudo dnf install gnome-shell-extension-appindicator
```

## Modo dev (rodar sem instalar)

```bash
cd /home/marcos/Projetos/fingerprint-manager
./run.sh
# o script compila o schema local (data/) e exporta
# GSETTINGS_SCHEMA_DIR + PYTHONPATH automaticamente

# opções úteis:
./run.sh --background        # inicia sem apresentar a janela (autostart)
GSETTINGS_SCHEMA_DIR=data gsettings set org.example.fingerprint-manager show-tray false
GSETTINGS_SCHEMA_DIR=data gsettings reset org.example.fingerprint-manager show-tray
```

Atalhos: `Ctrl+R` recarrega · `Ctrl+Q` sai · `Esc` cancela enroll.

Diagnóstico:

```bash
fprintd-list $USER
busctl --session list | grep -i statusnotifier   # vazio = sem host, esperado no GNOME
journalctl --user -f
```

## Instalar o RPM no Fedora

### Opção A — instalar o .rpm pronto

```bash
sudo dnf install ./dist/fingerprint-manager-0.1.0-1.fc*.noarch.rpm
glib-compile-schemas /usr/share/glib-2.0/schemas   # o %post já faz isso
fingerprint-manager
```

### Opção B — gerar o RPM a partir do source

```bash
sudo dnf install rpmdevtools rpm-build
rpmdev-setuptree
VERSION=0.1.0
tar --exclude=.git -czf ~/rpmbuild/SOURCES/fingerprint-manager-$VERSION.tar.gz \
  --transform "s,^,fingerprint-manager-$VERSION/," \
  main.py backend ui data run.sh README.md PLANO.md packaging/fingerprint-manager.spec
rpmbuild -ba packaging/fingerprint-manager.spec
# o rpm sai em ~/rpmbuild/RPMS/noarch/
sudo dnf install ~/rpmbuild/RPMS/noarch/fingerprint-manager-*.rpm
```

O que o pacote instala:

| Arquivo | Destino |
|---|---|
| `fingerprint-manager` (launcher) | `/usr/bin/` |
| app (`main.py`, `backend/`, `ui/`) | `/usr/share/fingerprint-manager/` |
| schema GSettings | `/usr/share/glib-2.0/schemas/` |
| atalho | `/usr/share/applications/fingerprint-manager.desktop` |

Autostart opcional (pela página Tray do app ou manual):

```bash
cp /usr/share/applications/fingerprint-manager.desktop \
   ~/.config/autostart/fingerprint-manager.desktop
```

## Layout do repo

```
fingerprint-manager/
  PLANO.md                # arquitetura + spec UI/UX normativa
  main.py                 # Adw.Application, --background, single-instance
  backend/fprintd.py      # GetDevices, props, ListEnrolledFingers (Gio.DBusProxy)
  backend/pam.py          # wrapper authselect async + pkexec
  ui/window.py            # PreferencesWindow: 5 páginas + toasts
  ui/enroll_view.py       # Vte embutido para enroll/verify
  ui/tray.py              # SNI puro-D-Bus (sem Gtk3)
  data/*.gschema.xml      # show-tray, refresh, device-path
  data/*.desktop
  packaging/*.spec        # RPM Fedora
  run.sh                  # modo dev
```

## Notas honestas

- **Tray no GNOME 48–50 Wayland:** não existe tray nativo; sem a extensão
  AppIndicator o indicador registra mas não aparece. É opcional por desenho.
- **Goodix:** precisa de `libfprint-tod` via COPR (ver Ajuda no app).
- `NoEnrolledPrints` = zero digitais, não é erro.
