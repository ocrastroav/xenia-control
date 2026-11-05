// clevo-fanctl.c - control de ventiladores Clevo/Tongfang (XENIA 15G) via comando EC 0x99
// Protocolo basado en clevo-indicator (SkyLandTW). 3 ventiladores (indices 1,2,3).
// Solo Fan1 (0xD0/D1) y Fan2 (0xD2/D3) exponen rpm; el central se comanda a ciegas.
//
// Compilar:  gcc -O2 -o clevo-fanctl clevo-fanctl.c
// Uso (root):
//   clevo-fanctl read                 -> temps + rpm + duty actual
//   clevo-fanctl set <idx 1-3> <0-100>
//   clevo-fanctl setall <0-100>
//   clevo-fanctl auto                 -> daemon con curva de temperatura (lo usa systemd)
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <unistd.h>
#include <signal.h>
#include <time.h>
#include <sys/io.h>
#include <sys/stat.h>

#define STATUS_PATH  "/run/clevo-fand.status"
#define CONTROL_PATH "/run/clevo-fand.control"

#define EC_SC   0x66
#define EC_DATA 0x62
#define IBF 1
#define OBF 0
#define EC_SC_READ_CMD 0x80

#define REG_CPU_TEMP 0x07
#define REG_GPU_TEMP 0xCD

static int ec_io_wait(const uint32_t port, const uint32_t flag, const char value) {
    uint8_t data = inb(port);
    int i = 0;
    while ((((data >> flag) & 0x1) != value) && (i++ < 100)) { usleep(1000); data = inb(port); }
    if (i >= 100) { fprintf(stderr, "wait_ec timeout port 0x%x\n", port); return 1; }
    return 0;
}
static uint8_t ec_io_read(const uint32_t port) {
    ec_io_wait(EC_SC, IBF, 0); outb(EC_SC_READ_CMD, EC_SC);
    ec_io_wait(EC_SC, IBF, 0); outb(port, EC_DATA);
    ec_io_wait(EC_SC, OBF, 1);
    return inb(EC_DATA);
}
static int ec_io_do(const uint32_t cmd, const uint32_t port, const uint8_t value) {
    ec_io_wait(EC_SC, IBF, 0); outb(cmd, EC_SC);
    ec_io_wait(EC_SC, IBF, 0); outb(port, EC_DATA);
    ec_io_wait(EC_SC, IBF, 0); outb(value, EC_DATA);
    return ec_io_wait(EC_SC, IBF, 0);
}
static int rpm(int hi_reg, int lo_reg) {
    int raw = (ec_io_read(hi_reg) << 8) + ec_io_read(lo_reg);
    return raw > 0 ? 2156220 / raw : 0;
}
static void set_fan(int idx, int pct) {
    if (pct < 0) pct = 0;
    if (pct > 100) pct = 100;
    uint8_t v = (uint8_t)(pct / 100.0 * 255.0);
    ec_io_do(0x99, idx, v);
}
static void set_all(int pct) { for (int i = 1; i <= 3; i++) set_fan(i, pct); }

// ---- Curva de temperatura con histeresis (temp mayor de CPU/GPU -> duty%) ----
typedef struct { int up; int down; int duty; } step_t;
static step_t curve[] = {
    {   0,   0,  35 },   // piso de seguridad
    {  55,  48,  45 },
    {  65,  58,  55 },
    {  72,  66,  65 },
    {  78,  73,  78 },
    {  84,  79,  90 },
    {  90,  85, 100 },
};
static const int NCURVE = sizeof(curve) / sizeof(curve[0]);
static int cur_level = 0;

static int curve_duty(int t) {
    while (cur_level < NCURVE - 1 && t >= curve[cur_level + 1].up) cur_level++;
    while (cur_level > 0 && t <= curve[cur_level].down) cur_level--;
    return curve[cur_level].duty;
}

static volatile sig_atomic_t running = 1;
static void on_sig(int s) { (void)s; running = 0; }

// Control via archivo: contenido "auto" (curva) o un numero 0-100 (manual).
static int read_control(void) {
    FILE *f = fopen(CONTROL_PATH, "r");
    if (!f) return -1;
    char buf[32] = {0};
    if (!fgets(buf, sizeof buf, f)) { fclose(f); return -1; }
    fclose(f);
    if (strncmp(buf, "auto", 4) == 0) return -1;
    int v = atoi(buf);
    if (v < 0) v = 0;
    if (v > 100) v = 100;
    return v;
}
static void ensure_control(void) {
    if (access(CONTROL_PATH, F_OK) != 0) {
        FILE *f = fopen(CONTROL_PATH, "w");
        if (f) { fputs("auto\n", f); fclose(f); }
    }
    chmod(CONTROL_PATH, 0666);   // escribible por la GUI (usuario normal)
}
static void write_status(int cpu, int gpu, int r1, int r2, const char *mode, int duty) {
    FILE *f = fopen(STATUS_PATH ".tmp", "w");
    if (!f) return;
    fprintf(f, "cpu=%d\ngpu=%d\nrpm1=%d\nrpm2=%d\nmode=%s\nduty=%d\n",
            cpu, gpu, r1, r2, mode, duty);
    fclose(f);
    rename(STATUS_PATH ".tmp", STATUS_PATH);
    chmod(STATUS_PATH, 0644);
}

static int daemon_loop(void) {
    signal(SIGTERM, on_sig);
    signal(SIGINT, on_sig);
    ensure_control();
    int last = -1;
    int ticks = 0;
    while (running) {
        int cpu = ec_io_read(REG_CPU_TEMP);
        int gpu = ec_io_read(REG_GPU_TEMP);
        int t = cpu > gpu ? cpu : gpu;
        int ctl = read_control();
        int d;
        const char *mode;
        if (ctl < 0) { d = curve_duty(t); mode = "auto"; }
        else         { d = ctl;           mode = "manual"; }
        // aplica al cambiar, y re-afirma cada ~30s por si el EC se reinicia
        if (d != last || (ticks % 15) == 0) { set_all(d); last = d; }
        write_status(cpu, gpu, rpm(0xD0, 0xD1), rpm(0xD2, 0xD3), mode, d);
        ticks++;
        sleep(2);
    }
    set_all(70);   // fallback seguro al detener el servicio
    return 0;
}

int main(int argc, char **argv) {
    if (ioperm(EC_DATA, 1, 1) || ioperm(EC_SC, 1, 1)) {
        perror("ioperm (ejecuta con sudo)");
        return 1;
    }
    if (argc < 2) {
        printf("uso:\n  %s read\n  %s set <idx 1-3> <0-100>\n  %s setall <0-100>\n  %s auto\n",
               argv[0], argv[0], argv[0], argv[0]);
        return 1;
    }
    if (!strcmp(argv[1], "read")) {
        printf("CPU temp       = %d C\n", ec_io_read(REG_CPU_TEMP));
        printf("GPU temp       = %d C\n", ec_io_read(REG_GPU_TEMP));
        printf("duty reg 0xCE  = %d/255\n", ec_io_read(0xCE));
        printf("Fan1 (0xD0/D1) = %d rpm\n", rpm(0xD0, 0xD1));
        printf("Fan2 (0xD2/D3) = %d rpm\n", rpm(0xD2, 0xD3));
        return 0;
    }
    if (!strcmp(argv[1], "set") && argc == 4) {
        int idx = atoi(argv[2]), pct = atoi(argv[3]);
        set_fan(idx, pct);
        printf("Enviado: 0x99 idx=%d duty=%d%%\n", idx, pct);
        return 0;
    }
    if (!strcmp(argv[1], "setall") && argc == 3) {
        int pct = atoi(argv[2]);
        set_all(pct);
        printf("Enviado: 0x99 a idx 1,2,3 duty=%d%%\n", pct);
        return 0;
    }
    if (!strcmp(argv[1], "auto")) {
        return daemon_loop();
    }
    printf("argumentos invalidos\n");
    return 1;
}
