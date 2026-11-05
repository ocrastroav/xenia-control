#!/usr/bin/env bash
# ============================================================================
#  XENIA Control - Instalador maestro
#  Ventiladores (3) + GPU 105W + CPU turbo, con cambio auto AC/bateria y GUI.
#  Para: XENIA 15G (Tongfang/Clevo, i7-14700HX + RTX 4060) en Ubuntu.
#  Uso:  sudo bash install.sh            (instalar / actualizar)
#        sudo bash install.sh --uninstall
# ============================================================================
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
BIN=/usr/local/bin
SYSD=/etc/systemd/system
APPS=/usr/share/applications

if [[ $EUID -ne 0 ]]; then echo "Ejecuta con sudo:  sudo bash $0"; exit 1; fi

# --------------------------------------------------------------- desinstalar
if [[ "${1:-}" == "--uninstall" ]]; then
  echo "== Desinstalando =="
  systemctl disable --now clevo-fand.service clevo-profiled.service 2>/dev/null || true
  systemctl disable clevo-profiled-resume.service 2>/dev/null || true
  rm -f "$SYSD"/clevo-fand.service "$SYSD"/clevo-profiled.service "$SYSD"/clevo-profiled-resume.service
  rm -f "$BIN"/clevo-fanctl "$BIN"/clevo-acpi-control "$BIN"/clevo-profiled "$BIN"/xenia-control
  rm -f "$APPS"/xenia-control.desktop "$APPS"/clevo-fan-gui.desktop "$APPS"/clevo-profile-gui.desktop
  systemctl daemon-reload
  echo "Hecho. (Se conservan /etc/clevo-profile.conf y la config del kernel.)"
  exit 0
fi

echo "== 1/7  Dependencias (apt) =="
export DEBIAN_FRONTEND=noninteractive
apt-get update -y >/dev/null 2>&1 || true
apt-get install -y build-essential dkms "linux-headers-$(uname -r)" \
                   acpi-call-dkms python3-gi gir1.2-gtk-3.0 >/dev/null
echo "   ok"

echo "== 2/7  Modulo acpi_call al arranque =="
echo acpi_call > /etc/modules-load.d/acpi_call.conf
modprobe acpi_call 2>/dev/null || true

echo "== 3/7  Compilando control de ventiladores =="
gcc -O2 -o "$BIN/clevo-fanctl" "$DIR/clevo-fanctl.c"

echo "== 4/7  Instalando binarios =="
install -m 755 "$DIR/clevo-acpi-control"    "$BIN/clevo-acpi-control"
install -m 755 "$DIR/clevo-profiled"        "$BIN/clevo-profiled"
install -m 755 "$DIR/xenia-control-gui.py"  "$BIN/xenia-control"
install -Dm 644 "$DIR/xenia-control.svg"    /usr/share/icons/hicolor/scalable/apps/xenia-control.svg
[[ -e /etc/clevo-profile.conf ]] || install -m 644 "$DIR/clevo-profile.conf" /etc/clevo-profile.conf

echo "== 5/7  Limpiando instalaciones previas sueltas =="
systemctl disable --now clevo-performance.service 2>/dev/null || true
systemctl disable clevo-performance-resume.service 2>/dev/null || true
rm -f "$SYSD"/clevo-performance.service "$SYSD"/clevo-performance-resume.service
rm -f "$APPS"/clevo-fan-gui.desktop "$APPS"/clevo-profile-gui.desktop

echo "== 6/7  Servicios systemd =="
cat > "$SYSD/clevo-fand.service" <<'EOF'
[Unit]
Description=XENIA - control de ventiladores
After=multi-user.target
[Service]
Type=simple
ExecStart=/usr/local/bin/clevo-fanctl auto
Restart=on-failure
RestartSec=3
[Install]
WantedBy=multi-user.target
EOF

cat > "$SYSD/clevo-profiled.service" <<'EOF'
[Unit]
Description=XENIA - perfil rendimiento (GPU/CPU, auto AC/bateria)
After=multi-user.target
[Service]
Type=simple
ExecStartPre=/sbin/modprobe acpi_call
ExecStart=/usr/local/bin/clevo-profiled
Restart=on-failure
RestartSec=3
[Install]
WantedBy=multi-user.target
EOF

cat > "$SYSD/clevo-profiled-resume.service" <<'EOF'
[Unit]
Description=XENIA - reaplicar perfil al reanudar
After=suspend.target hibernate.target hybrid-sleep.target suspend-then-hibernate.target
[Service]
Type=oneshot
ExecStart=/bin/systemctl restart clevo-profiled.service
[Install]
WantedBy=suspend.target hibernate.target hybrid-sleep.target suspend-then-hibernate.target
EOF

cat > "$APPS/xenia-control.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=XENIA Control
Comment=Ventiladores, GPU y rendimiento
Exec=/usr/local/bin/xenia-control
Icon=xenia-control
Terminal=false
Categories=System;Settings;
EOF

# refrescar caches de iconos y lanzadores
gtk-update-icon-cache -f /usr/share/icons/hicolor >/dev/null 2>&1 || true
update-desktop-database >/dev/null 2>&1 || true

echo "== 7/7  Activando servicios =="
systemctl daemon-reload
systemctl enable clevo-fand.service clevo-profiled.service clevo-profiled-resume.service >/dev/null 2>&1
systemctl restart clevo-fand.service clevo-profiled.service

sleep 4
echo
echo "========================= LISTO ========================="
systemctl is-active clevo-fand.service    | sed 's/^/  clevo-fand    : /'
systemctl is-active clevo-profiled.service | sed 's/^/  clevo-profiled: /'
echo "  --- ventiladores ---"; cat /run/clevo-fand.status 2>/dev/null | sed 's/^/    /' || echo "    (sin estado aun)"
echo "  --- rendimiento  ---"; cat /run/clevo-profile.status 2>/dev/null | sed 's/^/    /' || echo "    (sin estado aun)"
echo
echo "  GUI:  busca 'XENIA Control' en el menu, o corre:  xenia-control"
echo "  CLI:  clevo-fanctl read | clevo-acpi-control status"
echo "========================================================="
