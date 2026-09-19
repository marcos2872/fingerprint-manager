# Fingerprint Manager — Plano do Projeto

App GTK4/Adwaita com tray próprio (sem extensão GNOME Shell), para gerenciamento
de desbloqueio e cadastro de impressão digital. Tray desativável.

Local: `/home/marcos/Projetos/fingerprint-manager/`
Data: 2026-09-19
Máquina de referência: Fedora, GNOME 50.4, authselect `local with-fingerprint`,
leitor Validity VFS5011 sem digitais cadastradas.

## 1. Decisão: app em vez de extensão

- Extensão roda dentro do `gnome-shell`: qualquer chamada bloqueante congela a top bar.
- `extension.js` não pode usar Gtk/Adw (só St/Clutter); tela rica só caberia no
  `prefs.js` (processo separado, ruim para fluxo interativo de enroll).
- App GTK4 permite janela real, Vte embutido, diálogo polkit normal e não derruba
  a sessão em caso de falha.

## 2. Restrição honesta do tray no GNOME 48–50 Wayland

- Não existe tray nativo para app. Protocolo: `StatusNotifierItem`
  (`org.kde.StatusNotifierWatcher` no session bus).
- Verificado nesta máquina: `no sn watcher running` e pacote
  `gnome-shell-extension-appindicator` NÃO instalado.
- Sem host, o indicador registra mas não aparece. O app funciona 100% como janela.
- Com host instalado (extensão padrão do Ubuntu/Fedora opcional), o tray aparece.
- Por isso o tray é opcional e desligável, nunca obrigatório.

## 3. Compatibilidade com outros sensores (genérico)

Nada de VFS5011 hardcoded. Tudo via system bus `net.reactivated.Fprint`:

- `Manager.GetDevices() -> ao` + `GetDefaultDevice() -> o`
- Props por device (`org.freedesktop.DBus.Properties`): `name`, `scan-type`
  (press vs swipe), `num-enroll-stages`, `finger-present`
- `Device.ListEnrolledFingers(username) -> as`
  - Erro `NoEnrolledPrints` = zero digitais, não falha.
- Dedos padrão: left/right-thumb/index-finger/middle-finger/ring-finger/little-finger
- Casos: Goodix (precisa `libfprint-tod` via COPR), Synaptics, ELAN, multi-leitor
  (combo auto + lista), sem leitor (lista vazia).

Cadastro/verificação delegados (não reimplementar Claim/EnrollStart):

- `fprintd-enroll -f <dedo>`, `fprintd-verify`, `fprintd-list $USER`, `fprintd-delete`
- Atalho `gnome-control-center user-accounts` (fluxo oficial)

## 4. PAM (liga/desliga desbloqueio)

Fedora = `authselect`, nunca editar `/etc/pam.d` na mão:

- Leitura: `authselect current` + `authselect is-feature-enabled with-fingerprint`
- Liga: `pkexec authselect enable-feature with-fingerprint --backup=pre-fprint && pkexec authselect apply-changes -b`
- Desliga: `pkexec authselect disable-feature with-fingerprint ...`
- Tudo async via `subprocess` (não travar UI). `pkexec` abre diálogo de senha.
- Sem `authselect` (ex. Ubuntu com pam-auth-update): desabilitar switch com aviso.
- Afeta `gdm-fingerprint`, `sudo`, `login` na próxima autenticação.

## 5. Stack

- Python 3 + GTK4 + libadwaita (verificado: `gtk4+adw ok`)
- Terminal: `ptyxis` nesta máquina; no app usar `Vte` embutido (sem terminal externo)
- Tray: módulo `tray.py` isolado, StatusNotifierItem puro-D-Bus
  (`org.kde.StatusNotifierItem` + `com.canonical.dbusmenu`), sem Gtk3.
  - Motivo: `AppIndicator3` (libappindicator-gtk3) é GTK3 e mistura toolkits no app GTK4.
- GSettings `org.example.fingerprint-manager`: `show-tray` (bool, default true),
  `refresh` (int 5..120, default 30), `device-path` (str default `auto`)

## 6. Estrutura

```
fingerprint-manager/
  PLANO.md                # este arquivo
  main.py                 # Adw.Application, --background, single-instance
  backend/fprintd.py      # GetDevices, props, ListEnrolledFingers (Gio.DBusProxy)
  backend/pam.py          # wrapper authselect async + pkexec
  ui/window.py            # ApplicationWindow + ViewStack com PreferencesPages (6.1.2)
                        # (PreferencesWindow/AdwWindow não permite titlebar custom nem
                        #  Banner no topo, ambos exigidos pela spec — mesmos componentes)
  ui/enroll_view.py       # Vte embutido para enroll/verify
  ui/tray.py              # SNI puro-D-Bus, liga/desliga via show-tray
  data/org.example.fingerprint-manager.gschema.xml
  data/fingerprint-manager.desktop
  run.sh
  README.md
```

Janela (gerenciamento total):

1. Dispositivo: combo auto+lista, Recarregar, nome/scan-type/stages
2. Digitais: lista cadastrada, Cadastrar / Verificar / Apagar todas, Abrir Ajustes
3. Desbloqueio PAM: switch with-fingerprint + saída de `authselect current`
4. Tray: switch `show-tray` + status do watcher no bus
5. Ajuda: logs + dica Goodix-TOD

Menu do tray: Estado, Abrir gerenciador, Cadastrar, Verificar, PAM on/off, Sair.

Autostart opcional: `~/.config/autostart/fingerprint-manager.desktop` com `--background`.

## 6.1. UI/UX — Especificação obrigatória (seguir à risca)

Referência: GNOME HIG + libadwaita. Nada de estilo custom fora do Adwaita.
Objetivo: gerenciamento total em ≤3 cliques, nunca travar, sempre indicar estado.

### 6.1.1. Princípios inegociáveis

1. Janela única, opaca, adaptativa. Single-instance (`Adw.Application`).
2. Toda I/O (D-Bus `net.reactivated.Fprint`, `authselect`, `pkexec`) é async.
   Nenhum callback bloqueante na thread da UI.
3. Sem cor hardcoded. Usar só tokens Adwaita (`accent_bg_color`, `error_bg_color`,
   `success_color`, etc). Dark/light automático.
4. Sem GTK3 misturado. Sem `GtkTreeView`, `GtkMenu` antigo, popup custom,
   terminal externo ou `AppIndicator3`.
5. Texto em português, via `gettext`, sem concatenar frases. Sem jargão D-Bus
   exposto ao usuário final.

### 6.1.2. Shell da janela

- Classe: `Adw.PreferencesWindow` dentro de `Adw.ToastOverlay` (toasts no root).
- `default-size: 880x620`, `minimum: 640x480`. Sem scroll horizontal até 640px.
- `HeaderBar`:
  - `title: Fingerprint Manager`
  - Esquerda: botão `Recarregar` (`view-refresh-symbolic`, tooltip `Recarregar leitores e digitais`).
  - Direita: menu `≡` com: `Abrir Ajustes do Sistema`, `Copiar logs`, `Sobre`.
- `Adw.Banner` persistente no topo, mostrado quando:
  - `sem watcher SNI no session bus` → `Tray indisponível neste GNOME — o app funciona como janela. [Entendi]`
  - `GetDevices == []` → `Nenhum leitor encontrado. Verifique drivers. [Ver ajuda]`
  - Só um banner por vez, prioridade: sem-leitor > sem-watcher. Dispensável, mas volta se estado persistir após reload.
- Navegação lateral automática do `PreferencesWindow`, 5 pages fixas nesta ordem:
  1. `Dispositivo` — `hardware-usb-symbolic`
  2. `Digitais` — `fingerprint-symbolic`
  3. `Desbloqueio` — `security-high-symbolic`
  4. `Tray` — `status-symbolic`
  5. `Ajuda` — `help-about-symbolic`

### 6.1.3. Página 1 — Dispositivo

- `PreferencesGroup "Leitor"`:
  - `Adw.ComboRow "Leitor"`: `auto (padrão)` + lista `name + path curto`. Persistido em `device-path`.
    Trocar dispara reload de props + lista de dedos, com spinner inline na row.
  - `Adw.ActionRow "Modelo"` (subtitle = `name`), `"Tipo"` (subtitle = `press | swipe`),
    `"Etapas"` (subtitle = `num-enroll-stages`), `"Dedo presente"` (subtitle = `sim/não`, dot verde/cinza).
  - Props em fonte monospace no subtitle, nunca em caixa alta.
- Estado vazio (`GetDevices == []`):
  - `Adw.StatusPage`, icon `computer-fail-symbolic`, title `Nenhum leitor`,
    description `Conecte um leitor ou instale o driver. Goodix precisa de libfprint-tod via COPR.`,
    botão `Recarregar`.
- Estado carregando: rows com `sensitive=false` + `Gtk.Spinner` no sufixo. Nunca janela em branco.

### 6.1.4. Página 2 — Digitais (fluxo principal)

- `PreferencesGroup "X de 10 dedos cadastrados"` (conta `ListEnrolledFingers($USER)`).
- Lista: um `Adw.ActionRow` por dedo cadastrado, icon `fingerprint-symbolic`,
  title = nome amigável (`Indicador direito`), subtitle = id D-Bus (`right-index-finger`),
  sufixo botão `Apagar` (icon `user-trash-symbolic`, só hover/foco para não poluir).
- Vazio: `Adw.StatusPage`, icon `fingerprint-symbolic`, title `Nenhuma digital`,
  description `Cadastre ao menos um dedo para desbloquear com biometria.`,
  botão `Cadastrar (suggested-action)`.
- Barra de ações (rodapé do grupo, 4 botões, ordem fixa):
  1. `Cadastrar (suggested-action)` → abre EnrollView
  2. `Verificar` → abre VerifyView
  3. `Apagar todas (destructive-action)` → `Adw.AlertDialog` de confirmação
  4. `Abrir Ajustes` (flat) → `gnome-control-center user-accounts`
- Regra: `Cadastrar/Verificar` desabilitados se `GetDevices == []`. `Apagar todas`
  desabilitado se lista vazia. Tooltip explica o porquê quando desabilitado.

### 6.1.5. Enroll / Verify (página de navegação, não modal)

- `Adw.NavigationPage` separada com botão voltar. Título: `Cadastrar — Indicador direito`
  ou `Verificar digital`.
- Layout vertical, mesma janela:
  - Instrução no topo: `Encoste o dedo X vezes` ou `Deslize da ponta à base` (escolhe por `scan-type`).
    Nunca mostrar output cru do `fprintd-enroll` sem essa frase de contexto.
  - `Gtk.ProgressBar` com `etapas = num-enroll-stages` (ex. `2/5`).
  - `Vte.Terminal` readonly, altura mínima 180px, fonte monospace 12, scroll automático.
    É log técnico, não UI principal.
  - Rodapé: `Cancelar (flat)` à esquerda, `Concluir (suggested, disabled até sair 0)` à direita.
  - `Esc` = Cancelar (mata subprocesso). Fechar no meio = confirmação `AlertDialog`.
- Sucesso: fecha view, `Toast "Digital cadastrada"`, refresh lista + tooltip do tray.
- Falha/timeout: fica na view, banner `error` inline + botão `Tentar de novo`, log copiável.

### 6.1.6. Página 3 — Desbloqueio (PAM)

- `Adw.SwitchRow "Usar digital para login e sudo"`:
  - subtitle dinâmico: `Ativado (with-fingerprint)` | `Desativado` | `Aplicando...`.
  - Toggle dispara `pkexec authselect ...` async. Durante apply: switch `sensitive=false` + spinner.
  - Falha polkit (cancelado): volta ao estado anterior + `Toast "Autenticação cancelada"`.
- `Adw.ExpanderRow "Detalhe do sistema"` expandido por padrão:
  - `ActionRow` monospace com saída de `authselect current`, botão `Copiar`.
- Sem `authselect` no PATH: switch `sensitive=false`, subtitle
  `authselect não encontrado (ex. Ubuntu usa pam-auth-update)`. Nunca esconder a page.

### 6.1.7. Página 4 — Tray

- `Adw.SwitchRow "Mostrar ícone na barra"` ↔ GSettings `show-tray` (default `true`).
  Desligar remove SNI do bus sem fechar app, instantâneo.
- `Adw.ActionRow "Host StatusNotifier"`:
  - subtitle `Ativo — ícone visível` (dot verde) | `Ausente — app segue como janela` (dot cinza).
  - sufixo botão `Verificar` (re-checa `org.kde.StatusNotifierWatcher`).
- `Adw.SwitchRow "Iniciar com a sessão (--background)"` ↔ arquivo
  `~/.config/autostart/fingerprint-manager.desktop`. Criar/remover atomically.

### 6.1.8. Página 5 — Ajuda

- `ActionRow "Logs"` + botão `Copiar` (últimas 200 linhas `journalctl --user` filtradas).
- `ActionRow "Diagnóstico do tray"` + botão `Copiar` (`busctl --session list | grep StatusNotifier`).
- `ActionRow "Leitor Goodix?"` subtitle `Precisa de libfprint-tod via COPR. Veja README.`
- `ActionRow "Atalhos"` subtitle `Ctrl+R recarregar, Esc cancelar, Ctrl+Q sair`.

### 6.1.9. Tray (SNI) UX

- Ícone: `fingerprint-symbolic` monocromático. Nunca PNG colorido.
- Tooltip sempre atual: `Fingerprint: N digitais, PAM on/off, leitor nome-curto`.
- Menu ordem fixa, sem submenu:
  1. `Estado: N digitais, PAM on` (disabled, só informativo)
  2. separador
  3. `Abrir gerenciador`
  4. `Cadastrar...`
  5. `Verificar...`
  6. `PAM on/off` (checkbox)
  7. separador
  8. `Sair`
- Clique esquerdo = Abrir gerenciador. Clique do meio = Verificar. Sem watcher = menu inacessível, app 100% janela.

### 6.1.10. Tokens visuais, a11y, responsivo

- Tipografia: titles `title-1/2`, body padrão Adwaita. Monospace só para D-Bus/path/logs.
- Espaçamento: grupos com 12px, rows altura padrão Adwaita, nunca margem 0 ou >24px.
- Ícones: só `-symbolic`. Tamanho 16 para rows, 64+ para `StatusPage`.
- A11y: todo botão com `tooltip-text`, foco visível, navegação completa por teclado,
  contraste nativo, `AlertDialog` modal com `default` + `destructive` bem marcados.
- Responsivo: <720px empilha sufixos para baixo, `ComboRow` vira full-width, Vte mantém min-height com scroll.
- i18n: todas strings via `_()`, sem f-string com frase parcial. Ex.: `_("Cadastrar — {finger}")`.

### 6.1.11. Anti-patterns (proibido)

- Congelar UI, usar `os.system` sync, editar `/etc/pam.d` na mão, hardcodar VFS5011,
  mostrar `NoEnrolledPrints` como erro, esconder erro em console, usar cor hex,
  abrir `ptyxis` externo, misturar GTK3, toast sem ação quando ação é esperada.

## 7. Validação

- `python3 main.py` com VFS5011 (0 digitais) → cadastrar 1 dedo via Vte → tray atualiza
- `GSETTINGS_SCHEMA_DIR=data gsettings set org.example.fingerprint-manager show-tray false`
  → indicador some sem fechar o app
- `GetDevices=[]` → "sem leitor" + dica de driver quando aplicável
- Logs: `journalctl --user -f`; watcher: `busctl --session list | grep -i statusnotifier`

## 8. Decisões em aberto

1. Tray puro-D-Bus (GTK4 limpo, mais código) vs AppIndicator3 (menos código, arrasta GTK3)?
   - Proposta atual: puro-D-Bus.
2. Terminal embutido (Vte) vs abrir `ptyxis` externo? Proposta: Vte embutido.
3. Dependência opcional `gnome-shell-extension-appindicator` só para o ícone aparecer,
   ou app só-janela + notificação? Proposta: suportar ambos, com banner quando sem host.
