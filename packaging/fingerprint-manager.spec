Name:           fingerprint-manager
Version:        1.2.1
Release:        1%{?dist}
Summary:        Gerenciador de impressão digital (GTK4/Adwaita + fprintd + authselect)
License:        MIT
URL:            https://github.com/marcos2872/fingerprint-manager
Source0:        %{name}-%{version}.tar.gz

BuildArch:      noarch
BuildRequires:  desktop-file-utils
BuildRequires:  libappstream-glib
Requires:       python3, python3-gobject, gtk4, libadwaita, vte291-gtk4
Requires:       fprintd, authselect, polkit

%description
App GTK4/Adwaita para gerenciar cadastro e desbloqueio por impressão
digital via fprintd + authselect.

%prep
%setup -q

%install
mkdir -p %{buildroot}%{_bindir}
mkdir -p %{buildroot}%{_datadir}/%{name}
mkdir -p %{buildroot}%{_datadir}/glib-2.0/schemas
mkdir -p %{buildroot}%{_datadir}/applications
mkdir -p %{buildroot}%{_datadir}/metainfo
mkdir -p %{buildroot}%{_datadir}/dbus-1/services

install -m755 main.py %{buildroot}%{_datadir}/%{name}/main.py
cp -a backend ui assets %{buildroot}%{_datadir}/%{name}/
find %{buildroot}%{_datadir}/%{name} -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || :
install -m644 data/io.github.marcos2872.fingerprint-manager.gschema.xml \
  %{buildroot}%{_datadir}/glib-2.0/schemas/
install -m644 data/io.github.marcos2872.fingerprint-manager.desktop \
  %{buildroot}%{_datadir}/applications/
install -m644 data/io.github.marcos2872.fingerprint-manager.metainfo.xml \
  %{buildroot}%{_datadir}/metainfo/
install -m644 data/io.github.marcos2872.fingerprint-manager.service \
  %{buildroot}%{_datadir}/dbus-1/services/io.github.marcos2872.fingerprint-manager.service
mkdir -p %{buildroot}%{_datadir}/icons/hicolor/scalable/apps
install -m644 assets/icon.svg \
  %{buildroot}%{_datadir}/icons/hicolor/scalable/apps/fingerprint-manager.svg

cat > %{buildroot}%{_bindir}/fingerprint-manager <<'EOF'
#!/usr/bin/env bash
exec /usr/bin/python3 /usr/share/fingerprint-manager/main.py "$@"
EOF
chmod 755 %{buildroot}%{_bindir}/fingerprint-manager

%check
desktop-file-validate %{buildroot}%{_datadir}/applications/io.github.marcos2872.fingerprint-manager.desktop
appstream-util validate-relax %{buildroot}%{_datadir}/metainfo/io.github.marcos2872.fingerprint-manager.metainfo.xml

%post
glib-compile-schemas %{_datadir}/glib-2.0/schemas &>/dev/null || :
touch --no-create %{_datadir}/icons/hicolor &>/dev/null || :
gtk-update-icon-cache %{_datadir}/icons/hicolor &>/dev/null || :

%postun
gtk-update-icon-cache %{_datadir}/icons/hicolor &>/dev/null || :

%files
%{_bindir}/fingerprint-manager
%{_datadir}/%{name}/
%{_datadir}/glib-2.0/schemas/io.github.marcos2872.fingerprint-manager.gschema.xml
%{_datadir}/applications/io.github.marcos2872.fingerprint-manager.desktop
%{_datadir}/metainfo/io.github.marcos2872.fingerprint-manager.metainfo.xml
%{_datadir}/dbus-1/services/io.github.marcos2872.fingerprint-manager.service
%{_datadir}/icons/hicolor/scalable/apps/fingerprint-manager.svg

%changelog
* Sat Sep 19 2026 dev <dev@example.com> - 1.2.1-1
- Metainfo sem stock icon (appstream-util do %check rejeitava); loja usa o Icon= do .desktop via launchable
* Sun Sep 20 2026 dev <dev@example.com> - 1.2.0-1
- Publicável na loja: APP_ID válido, metainfo AppStream, service D-Bus; botão GitHub na Ajuda; docs de instalação via COPR
* Sat Sep 19 2026 dev <dev@example.com> - 1.1.0-1
- Ícone do app, toggle login cobre tela de bloqueio, suite pytest + CI, clean code, dev via uv
* Sat Sep 19 2026 dev <dev@example.com> - 1.0.0-1
- v1: toggles de digital por serviço, sem tray
* Sat Sep 19 2026 dev <dev@example.com> - 0.1.0-1
- Versão inicial (janela GTK4, Vte embutido)
