# XENIA Control

Control completo de **XENIA 15G** (barebone Tongfang/Clevo, i7-14700HX + RTX 4060) en Ubuntu:

- 🌀 **Ventiladores** (los 3) con curva de temperatura automática + control manual.
- 🎮 **GPU** desbloqueada a **105W** (perfil "performance" vía ACPI del fabricante).
- ⚡ **CPU** con Turbo + frecuencia máxima (y PL1/PL2 altos del perfil firmware).
- 🔌 Cambio **automático según corriente/batería** (performance enchufado, ahorro en batería).
- 🖥️ Una sola **GUI** con pestañas (Ventiladores + Rendimiento).

## Instalación (incluido tras formatear)

Respalda esta carpeta completa. En el equipo nuevo:

```bash
sudo bash install.sh
```

Instala dependencias (`build-essential`, `dkms`, headers del kernel, `acpi-call-dkms`,
`python3-gi`, `gir1.2-gtk-3.0`), compila, instala servicios y GUI, y arranca todo.

Requisitos: Ubuntu, Secure Boot **desactivado** (para que cargue `acpi_call` sin firmar),
estar en **corriente** para ver los 105W (en batería el firmware limita la GPU a 35W).

## Uso

- GUI: menú → **XENIA Control**, o `xenia-control`.
- Ventiladores CLI: `clevo-fanctl read` · `sudo clevo-fanctl setall 80`
- Perfil CLI: `sudo clevo-acpi-control status` · `sudo clevo-acpi-control set performance --force`
- Perfil en batería: edita `/etc/clevo-profile.conf` (`BAT_PROFILE=...`).

## Desinstalar

```bash
sudo bash install.sh --uninstall
```

## Notas técnicas

- Ventiladores: comando EC vendor `0x99` (índices 1/2/3) por I/O de puertos; solo 2 fans
  exponen rpm, el central se comanda a ciegas. tuxedo-drivers y NBFC **no** sirven en este EC.
- GPU: perfil firmware `\_SB.WMI.SCMD 0 0x79 0x19000002` (performance) autoriza `NPCF.CTGP`.
  `nvidia-smi -pl` está bloqueado en laptops con driver ≥550; esta es la vía correcta.
- CPU: `intel_pstate/no_turbo=0` + `scaling_max_freq=cpuinfo_max_freq`; PPD gestiona EPP.
- Al actualizar el kernel, vuelve a correr `sudo bash install.sh` (recompila el módulo de fans
  no aplica —es binario de usuario—, pero `acpi-call-dkms` se reconstruye solo vía DKMS).

Basado en: clevo-indicator (SkyLandTW), tuxedo-drivers (registros), SilverKurali/clevo-acpi-control.

## Licencia

**GPLv3** (ver `LICENSE`). Incluye y deriva de software bajo GPL:

- `clevo-acpi-control` © SilverKurali — GPLv3 (incluido sin cambios).
- `clevo-fanctl.c` — reimplementación propia del protocolo de clevo-indicator (SkyLandTW, GPL).
- Direcciones de registros de GPU tomadas de tuxedo-drivers (TUXEDO Computers, GPLv2+).

Sin garantía. Úsalo bajo tu propia responsabilidad: toca el EC y la potencia del hardware.
