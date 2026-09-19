# AGENTS.md — fingerprint-manager

Python + GTK4/libadwaita. Single-instance `Adw.Application` (`main.py`).
Lint: `ruff check`. Commits em Conventional Commits (`feat:`, `fix:`, `chore:`).
Testes pytest em `tests/`; CI no GitHub (`.github/workflows/tests.yml`).

## Rodar e verificar

- Dev: `./run.sh` (compila schemas, exporta `GSETTINGS_SCHEMA_DIR` + `PYTHONPATH`).
- Sem display, só dá para verificar imports, não rodar a UI:
  `GSETTINGS_SCHEMA_DIR=data PYTHONPATH=. python3 -c "import main, ui.window"`
- `python3 -m py_compile main.py backend/*.py ui/*.py` após qualquer edição.
- Lint: `ruff check .` (config em `pyproject.toml`: só F+E9, sem estilo).
  Instalar uma vez: `python3 -m pip install --user ruff`.
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

## Código limpo (vale para todo PR)

- Decisão vai em função pura testável (`backend/ui_state.py`); a janela
  (`ui/window.py`) só exibe. Novo `if/else` de label/estado no render?
  Extraia para `ui_state` + teste em `tests/test_ui_state.py`.
- Sem God class: cada página tem seu `_build_*_page`. Passou de ~400 linhas
  no arquivo ou o método faz 2 coisas? Quebre antes de estender.
- Sem duplicação: blocos thread+toast+refresh e truncamentos usam os helpers
  existentes (`_run_delete`, `ui_state.short`) em vez de copiar.
- Sem número mágico: timeouts e paths vivem em constantes no topo do módulo
  (`DBUS_TIMEOUT_MS`, `PKEXEC_TIMEOUT_S`, `SUBPROCESS_TIMEOUT_S`...).
- `except` sem `log` é proibido (`log.debug` no mínimo); `pass` puro, nunca.
- Sem código morto: removeu o uso, remova a função e o teste dela.
- Fonte única: `APP_ID`/`APP_VERSION` moram em `backend/version.py`;
  `main.py` e `ui/` importam de lá.

## CI / PR (obrigatório)

- Workflow `tests` roda a cada PR e push em `main` (container `fedora:latest`
  + `dnf install python3-gobject gtk4 libadwaita vte291-gtk4 python3-pytest`).
  Sem display: UI pula sozinha (`RUN_GUI_TESTS` ausente).
- `main` é protegida: check `tests` obrigatório, push direto é barrado.
  Fluxo sempre: branch → push da branch → `gh pr create` → merge após verde.
  Nunca commitar esperando pushear direto em `main`.

## Releases

Procedimento completo em `RELEASE.md` (versão em `backend/version.py` +
spec, build do RPM, release com descrição do que mudou + `.rpm` anexado).
Regra crítica: a tag (`vX.Y.Z`) precisa ser numericamente maior que
`APP_VERSION`, senão o aviso de update na aba Ajuda não dispara.

## Não fazer

- Não reintroduzir tray/StatusNotifier (removido de propósito; era a causa do freeze).
- `--background` em `main.py` é no-op mantido por compat com autostart antigo.
- `PLANO.md` foi deletado (obsoleto); `README.md` é a doc canônica.
