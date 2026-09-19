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
python3 -m pip install --user pytest   # só para rodar os testes
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

## Testes

```bash
pytest tests/                      # backend (headless, D-Bus e rede mockados)
RUN_GUI_TESTS=1 pytest tests/      # inclui UI (precisa de display)
```

Com `uv` (o `gi` vem do sistema, por isso `--system-site-packages`):

```bash
uv venv --system-site-packages     # uma vez
uv pip install --python .venv/bin/python pytest
.venv/bin/python -m pytest tests/
```

Fixtures PAM usam `FPRINT_PAM_DIR` (nunca encostam em `/etc/pam.d`).

Lint: `ruff check .` (`python3 -m pip install --user ruff` uma vez).

## Gerar e instalar o RPM (Fedora)

```bash
sudo dnf install rpmdevtools rpm-build
rpmdev-setuptree
VERSION=0.1.0
tar --exclude=.git -czf ~/rpmbuild/SOURCES/fingerprint-manager-$VERSION.tar.gz \
  --transform "s,^,fingerprint-manager-$VERSION/," \
  main.py backend ui data assets run.sh README.md AGENTS.md LICENSE RELEASE.md packaging/fingerprint-manager.spec
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
| atalho | `/usr/share/applications/org.example.fingerprint-manager.desktop` |

Autostart manual (abre a janela ao iniciar a sessão):

```bash
cp /usr/share/applications/org.example.fingerprint-manager.desktop \
   ~/.config/autostart/org.example.fingerprint-manager.desktop
```

## Desinstalar

```bash
sudo dnf remove fingerprint-manager
rm -f ~/.config/autostart/org.example.fingerprint-manager.desktop
# restos do modo dev (run.sh instala atalho + ícone locais):
rm -f ~/.local/share/applications/org.example.fingerprint-manager.desktop
rm -f ~/.local/share/icons/hicolor/scalable/apps/fingerprint-manager.svg
```

PAM: o `dnf remove` **não** desfaz as linhas de digital em `/etc/pam.d`.
Antes de desinstalar, desligue os dois switches na aba Desbloqueio —
ou restaure os backups manualmente (troque a data pela que o `ls` mostrar;
`<...>` não pode ir literal no comando, o shell interpreta como redireção):

```bash
ls /etc/pam.d/*.bak-fingerprint-manager-*
sudo cp /etc/pam.d/sudo.bak-fingerprint-manager-20260919-191157 /etc/pam.d/sudo
sudo cp /etc/pam.d/gdm-fingerprint.bak-fingerprint-manager-20260919-191128 /etc/pam.d/gdm-fingerprint
grep -r pam_fprintd /etc/pam.d/ || echo "limpo"
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
  assets/icon.svg         # ícone do app (hicolor scalable)
  packaging/*.spec        # RPM Fedora
  run.sh                  # modo dev
```

## Notas honestas

- **Goodix:** precisa de `libfprint-tod` via COPR (ver Ajuda no app).
- `NoEnrolledPrints` = zero digitais, não é erro.
- Login edita `/etc/pam.d/gdm-fingerprint` (tela de login) e
  `/etc/pam.d/gdm-password` (tela de bloqueio); sudo edita `/etc/pam.d/sudo`
  (linha `sufficient`: falha cai para senha, nunca trava o login).
  Backups em `/etc/pam.d/*.bak-fingerprint-manager-*`.
