# Releases — como publicar uma versão nova

## 1. Subir a versão no app (antes de tudo)

O aviso de "nova versão" na aba Ajuda compara a tag da release com
`APP_VERSION`. Se a tag não for maior, o app não notifica.

1. `backend/version.py` → `APP_VERSION = "X.Y.Z"` (o Sobre lê daqui sozinho).
2. `packaging/fingerprint-manager.spec` → campo `Version: X.Y.Z` + entrada
   no `%changelog` no mesmo estilo das anteriores.
3. Commit + push em `main`.

## 2. Gerar o RPM

```bash
sudo dnf install -y rpmdevtools rpm-build   # só na primeira vez
rpmdev-setuptree                            # só na primeira vez
VERSION=X.Y.Z
tar --exclude=.git --exclude=__pycache__ \
  -czf ~/rpmbuild/SOURCES/fingerprint-manager-$VERSION.tar.gz \
  --transform "s,^,fingerprint-manager-$VERSION/," \
  main.py backend ui data assets run.sh README.md AGENTS.md LICENSE RELEASE.md \
  packaging/fingerprint-manager.spec
rpmbuild -ba packaging/fingerprint-manager.spec
rpm -qlp ~/rpmbuild/RPMS/noarch/fingerprint-manager-$VERSION-*.noarch.rpm  # confere
```

## 3. Criar a release no GitHub

A release **sempre** leva descrição do que mudou + o `.rpm` anexado:

```bash
cat <<'NOTES' > /tmp/opencode/release-notes.md
# Fingerprint Manager vX.Y.Z

<1-2 frases do destaque>

- <mudança 1>
- <mudança 2>

## Instalar no Fedora

```bash
sudo dnf install ./fingerprint-manager-X.Y.Z-*.noarch.rpm
fingerprint-manager
```

Requer: `fprintd`, `authselect`, `polkit`, `gtk4`, `libadwaita`, `vte291-gtk4`.
NOTES
gh release create vX.Y.Z ~/rpmbuild/RPMS/noarch/fingerprint-manager-X.Y.Z-*.noarch.rpm \
  --title "vX.Y.Z" --notes-file /tmp/opencode/release-notes.md --target main
```

## 4. Conferir

- Release em `https://github.com/marcos2872/fingerprint-manager/releases`.
- Regra da tag: formato `vX.Y.Z` numérico e **maior que `APP_VERSION`**
  (ex: app em `1.0.0` + tag `v1.1.0` = notifica; tag `v1.0.0` = não notifica).
- O `.rpm` precisa ser gerado da árvore commitada (sem `git status` sujo).

## 5. Publicar no COPR (repo de terceiros)

O COPR **não** é o repo oficial do Fedora: o usuário precisa de
`dnf copr enable` uma vez antes do `dnf install`. O passo 2 já gera o
`.src.rpm` necessário (`~/rpmbuild/SRPMS/`).

```bash
sudo dnf install -y copr-cli   # só na primeira vez
```

Autenticação (só na primeira vez): entre em
`https://copr.fedorainfracloud.org` com a conta Fedora, copie
login/username/token em `https://copr.fedorainfracloud.org/api/` e
salve no **arquivo** `~/.config/copr` (atenção: é um arquivo, não um
diretório; seção `[copr-cli]`):

```ini
[copr-cli]
login = <login da página /api>
username = marcos2872
token = <token da página /api>
copr_url = https://copr.fedorainfracloud.org
```

```bash
chmod 600 ~/.config/copr
copr-cli whoami   # confere: deve imprimir o usuário
```

Criar o projeto (só na primeira vez; chroots atuais em
`copr-cli list-chroots`):

```bash
copr-cli create fingerprint-manager \
  --chroot fedora-43-x86_64 --chroot fedora-44-x86_64 \
  --description "Gerenciador de impressão digital (GTK4/Adwaita + fprintd)" \
  --instructions "sudo dnf copr enable marcos2872/fingerprint-manager && sudo dnf install fingerprint-manager"
```

Subir o build a cada release (usa o `.src.rpm` do passo 2):

```bash
VERSION=X.Y.Z
copr-cli build fingerprint-manager \
  ~/rpmbuild/SRPMS/fingerprint-manager-$VERSION-1.fc*.src.rpm
# acompanha até "succeeded" (pode interromper o watch com Ctrl+C)
```

Instalação pelo usuário final:

```bash
sudo dnf copr enable marcos2872/fingerprint-manager
sudo dnf install fingerprint-manager
```
