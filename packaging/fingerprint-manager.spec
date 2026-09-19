Name:           fingerprint-manager
Version:        1.0.0
Release:        1%{?dist}
Summary:        Gerenciador de impressão digital (GTK4/Adwaita + fprintd + authselect)
License:        MIT
URL:            https://github.com/anomalyco/opencode
Source0:        %{name}-%{version}.tar.gz

BuildArch:      noarch
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

install -m755 main.py %{buildroot}%{_datadir}/%{name}/main.py
cp -a backend ui %{buildroot}%{_datadir}/%{name}/
install -m644 data/org.example.fingerprint-manager.gschema.xml \
  %{buildroot}%{_datadir}/glib-2.0/schemas/
install -m644 data/org.example.fingerprint-manager.desktop \
  %{buildroot}%{_datadir}/applications/
mkdir -p %{buildroot}%{_datadir}/icons/hicolor/scalable/apps
install -m644 assets/icon.svg \
  %{buildroot}%{_datadir}/icons/hicolor/scalable/apps/fingerprint-manager.svg

cat > %{buildroot}%{_bindir}/fingerprint-manager <<'EOF'
#!/usr/bin/env bash
exec /usr/bin/python3 /usr/share/fingerprint-manager/main.py "$@"
EOF
chmod 755 %{buildroot}%{_bindir}/fingerprint-manager

%post
glib-compile-schemas %{_datadir}/glib-2.0/schemas &>/dev/null || :
touch --no-create %{_datadir}/icons/hicolor &>/dev/null || :
gtk-update-icon-cache %{_datadir}/icons/hicolor &>/dev/null || :

%postun
gtk-update-icon-cache %{_datadir}/icons/hicolor &>/dev/null || :

%files
%{_bindir}/fingerprint-manager
%{_datadir}/%{name}/
%{_datadir}/glib-2.0/schemas/org.example.fingerprint-manager.gschema.xml
%{_datadir}/applications/org.example.fingerprint-manager.desktop
%{_datadir}/icons/hicolor/scalable/apps/fingerprint-manager.svg

%changelog
* Sat Sep 19 2026 dev <dev@example.com> - 1.0.0-1
- v1: toggles de digital por serviço, sem tray
* Sat Sep 19 2026 dev <dev@example.com> - 0.1.0-1
- Versão inicial (janela GTK4, Vte embutido)
