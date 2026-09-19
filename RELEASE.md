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
