# Fingerprint Manager

App GTK4/Adwaita para gerenciar **cadastro de digitais e desbloqueio por biometria**
no Fedora/GNOME.

- Janela com 4 páginas: **Dispositivo · Digitais · Desbloqueio · Ajuda**
- Cadastro/verificação via `fprintd-enroll` / `fprintd-verify` em terminal **Vte embutido**
- Digital para **login (GDM) e sudo de forma independente**, via helper
  privilegiado (`pkexec`) com backup e validação
- Genérico: qualquer leitor do `net.reactivated.Fprint` (Validity, Goodix, Synaptics, ELAN…)

## Requisitos (Fedora)

```bash
sudo dnf install python3 python3-gobject gtk4 libadwaita vte291-gtk4 \
  fprintd authselect polkit gnome-control-center
```

## Modo dev (rodar sem instalar)

```bash
./run.sh
# compila o schema local (data/) e exporta
# GSETTINGS_SCHEMA_DIR + PYTHONPATH automaticamente
```

Atalhos: `Ctrl+R` recarrega · `Ctrl+Q` sai · `Esc` cancela enroll.

Diagnóstico:

```bash
fprintd-list $USER
journalctl --user -f
```

## Gerar e instalar o RPM (Fedora)

```bash
sudo dnf install rpmdevtools rpm-build
rpmdev-setuptree
VERSION=0.1.0
tar --exclude=.git -czf ~/rpmbuild/SOURCES/fingerprint-manager-$VERSION.tar.gz \
  --transform "s,^,fingerprint-manager-$VERSION/," \
  main.py backend ui data run.sh README.md packaging/fingerprint-manager.spec
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

Autostart manual (abre a janela ao iniciar a sessão):

```bash
cp /usr/share/applications/fingerprint-manager.desktop \
   ~/.config/autostart/fingerprint-manager.desktop
```

## Layout do repo

```
fingerprint-manager/
  main.py                 # Adw.Application single-instance
  backend/fprintd.py      # GetDevices, props, ListEnrolledFingers (Gio.DBusProxy)
  backend/pam.py          # leitura por serviço + escrita via helper/pkexec
  backend/pam_helper.py   # edita /etc/pam.d como root (backup + validação)
  ui/window.py            # ApplicationWindow + ViewStack com PreferencesPages
  ui/enroll_view.py       # Vte embutido para enroll/verify
  data/*.gschema.xml      # refresh, device-path
  data/*.desktop
  packaging/*.spec        # RPM Fedora
  run.sh                  # modo dev
```

## Notas honestas

- **Goodix:** precisa de `libfprint-tod` via COPR (ver Ajuda no app).
- `NoEnrolledPrints` = zero digitais, não é erro.
- Login edita `/etc/pam.d/gdm-fingerprint`, sudo edita `/etc/pam.d/sudo`
  (linha `sufficient`: falha cai para senha, nunca trava o login).
  Backups em `/etc/pam.d/*.bak-fingerprint-manager-*`.
