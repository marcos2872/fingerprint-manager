# AGENTS.md — fingerprint-manager

Python + GTK4/libadwaita. Single-instance `Adw.Application` (`main.py`).
Sem testes, sem CI, sem lint. Commits em Conventional Commits (`feat:`, `fix:`, `chore:`).

## Rodar e verificar

- Dev: `./run.sh` (compila schemas, exporta `GSETTINGS_SCHEMA_DIR` + `PYTHONPATH`).
- Sem display, só dá para verificar imports, não rodar a UI:
  `GSETTINGS_SCHEMA_DIR=data PYTHONPATH=. python3 -c "import main, ui.window"`
- `python3 -m py_compile main.py backend/*.py ui/*.py` após qualquer edição.
- Testes: `pytest tests/` (backend headless); UI só com display:
  `RUN_GUI_TESTS=1 pytest tests/`. Com uv: `uv venv --system-site-packages`
  uma vez + `uv pip install --python .venv/bin/python pytest` (o `gi` é do
  sistema; `.venv/` é gitignored). Fixtures PAM via `FPRINT_PAM_DIR`, nunca
  `/etc/pam.d` real.
- Alterou `data/*.gschema.xml`? Rode `glib-compile-schemas data/` (`data/gschemas.compiled` é artefato gitignored).
- Chaves GSettings atuais: `refresh`, `device-path`. `show-tray` foi removida — não reintroduzir.

## Regra de ouro da UI

Nunca D-Bus (`call_sync`) ou `subprocess` bloqueante na thread GTK.
Padrão: `run_in_thread(fn, on_done)` em `ui/window.py` + `GLib.idle_add` no retorno.
Todo `call_sync` usa timeout finito (`DBUS_TIMEOUT_MS = 5000` em `backend/fprintd.py`);
`-1` (infinito) já congelou a máquina uma vez.

## PAM (`backend/pam.py` + `backend/pam_helper.py`)

- Leitura é direta em `/etc/pam.d` (segue `include`/`substack`); escrita **só** via
  helper como root: `pkexec python3 pam_helper.py <login|sudo> <on|off>`.
- `login` edita `/etc/pam.d/gdm-fingerprint` (tela de login) e
  `/etc/pam.d/gdm-password` (tela de bloqueio), `sudo` edita `/etc/pam.d/sudo`.
  Linha sempre `sufficient` (falha cai para senha, nunca trava o login).
- Helper garante: idempotência, backup `.bak-fingerprint-manager-<data>`, escrita
  atômica (`tmp` + `os.replace`), recusa se o stack `auth` ficar vazio.
- Teste seguro sem root: `FPRINT_PAM_DIR=/tmp/fixtures` com cópias dos arquivos —
  `pam.py` e `pam_helper.py` honram a variável. Nunca rode o helper sem o
  override contra `/etc/pam.d` em testes.

## Releases

Procedimento completo em `RELEASE.md` (versão em `backend/version.py` +
spec, build do RPM, release com descrição do que mudou + `.rpm` anexado).
Regra crítica: a tag (`vX.Y.Z`) precisa ser numericamente maior que
`APP_VERSION`, senão o aviso de update na aba Ajuda não dispara.

## Não fazer

- Não reintroduzir tray/StatusNotifier (removido de propósito; era a causa do freeze).
- `--background` em `main.py` é no-op mantido por compat com autostart antigo.
- `PLANO.md` foi deletado (obsoleto); `README.md` é a doc canônica.
