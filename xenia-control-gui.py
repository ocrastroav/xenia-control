#!/usr/bin/python3
# XENIA Control - GUI unificada (ventiladores + rendimiento).
# Lee /run/clevo-fand.status y /run/clevo-profile.status;
# escribe /run/clevo-fand.control y /run/clevo-profile.control (sin root).
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib

FAN_STATUS = "/run/clevo-fand.status"
FAN_CONTROL = "/run/clevo-fand.control"
PROF_STATUS = "/run/clevo-profile.status"
PROF_CONTROL = "/run/clevo-profile.control"

PROFILES = [
    ("auto",          "Auto (según energía)"),
    ("performance",   "Rendimiento  (GPU 105W)"),
    ("entertainment", "Entretenimiento  (GPU 70W)"),
    ("saving",        "Ahorro"),
    ("quiet",         "Silencioso"),
]


def read_status(path):
    d = {}
    try:
        with open(path) as f:
            for line in f:
                if "=" in line:
                    k, v = line.strip().split("=", 1)
                    d[k] = v
    except OSError:
        return None
    return d


def write_control(path, v):
    try:
        with open(path, "w") as f:
            f.write(str(v) + "\n")
        return True
    except OSError:
        return False


class FanTab(Gtk.Grid):
    def __init__(self):
        super().__init__(column_spacing=12, row_spacing=10, margin=12)
        self._sync = False
        self.lbl = {k: Gtk.Label(label="—", xalign=0) for k in ("cpu", "gpu", "f1", "f2", "duty")}

        def row(r, title, w):
            self.attach(Gtk.Label(label=title, xalign=0), 0, r, 1, 1)
            self.attach(w, 1, r, 2, 1)
        row(0, "CPU:", self.lbl["cpu"])
        row(1, "GPU:", self.lbl["gpu"])
        row(2, "Fan 1 (lateral):", self.lbl["f1"])
        row(3, "Fan 2 (lateral):", self.lbl["f2"])
        row(4, "Duty / modo:", self.lbl["duty"])
        self.attach(Gtk.Label(label="(el fan central se comanda sin lectura de rpm)", xalign=0), 0, 5, 3, 1)
        self.attach(Gtk.Separator(), 0, 6, 3, 1)

        self.rb_auto = Gtk.RadioButton.new_with_label_from_widget(None, "Automático (curva)")
        self.rb_manual = Gtk.RadioButton.new_with_label_from_widget(self.rb_auto, "Manual")
        self.rb_auto.connect("toggled", self.on_mode)
        self.attach(self.rb_auto, 0, 7, 3, 1)
        self.attach(self.rb_manual, 0, 8, 3, 1)

        self.scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 5)
        self.scale.set_value(60)
        self.scale.set_hexpand(True)
        for p in (0, 25, 50, 75, 100):
            self.scale.add_mark(p, Gtk.PositionType.BOTTOM, str(p))
        self.scale.connect("value-changed", self.on_slider)
        self.attach(self.scale, 0, 9, 3, 1)

        box = Gtk.Box(spacing=6)
        for name, val in (("Silencioso 35%", 35), ("Medio 60%", 60), ("Turbo 100%", 100)):
            b = Gtk.Button(label=name)
            b.connect("clicked", self.on_preset, val)
            box.pack_start(b, True, True, 0)
        self.attach(box, 0, 10, 3, 1)

        self.msg = Gtk.Label(xalign=0)
        self.attach(self.msg, 0, 11, 3, 1)

    def on_mode(self, _b):
        if self._sync:
            return
        if self.rb_auto.get_active():
            self.scale.set_sensitive(False)
            write_control(FAN_CONTROL, "auto")
        else:
            self.scale.set_sensitive(True)
            write_control(FAN_CONTROL, int(self.scale.get_value()))

    def on_slider(self, s):
        if self._sync:
            return
        if self.rb_manual.get_active():
            write_control(FAN_CONTROL, int(s.get_value()))

    def on_preset(self, _b, val):
        self._sync = True
        self.rb_manual.set_active(True)
        self.scale.set_value(val)
        self._sync = False
        self.scale.set_sensitive(True)
        write_control(FAN_CONTROL, val)

    def refresh(self):
        st = read_status(FAN_STATUS)
        if not st:
            self.msg.set_markup("<span foreground='red'>Servicio clevo-fand no activo</span>")
            return
        self.lbl["cpu"].set_text("%s °C" % st.get("cpu", "—"))
        self.lbl["gpu"].set_text("%s °C" % st.get("gpu", "—"))
        self.lbl["f1"].set_text("%s rpm" % st.get("rpm1", "—"))
        self.lbl["f2"].set_text("%s rpm" % st.get("rpm2", "—"))
        self.lbl["duty"].set_text("%s %%  (%s)" % (st.get("duty", "—"), st.get("mode", "")))
        self.msg.set_text("")
        self._sync = True
        if st.get("mode") == "auto":
            self.rb_auto.set_active(True)
            self.scale.set_sensitive(False)
        else:
            self.rb_manual.set_active(True)
            self.scale.set_sensitive(True)
        self._sync = False


class PerfTab(Gtk.Grid):
    def __init__(self):
        super().__init__(column_spacing=10, row_spacing=8, margin=12)
        self._sync = False
        self.lbl_ac = Gtk.Label(xalign=0)
        self.lbl_cur = Gtk.Label(xalign=0)
        self.lbl_cpu = Gtk.Label(xalign=0)
        self.attach(Gtk.Label(label="Energía:", xalign=0), 0, 0, 1, 1)
        self.attach(self.lbl_ac, 1, 0, 1, 1)
        self.attach(Gtk.Label(label="Perfil activo:", xalign=0), 0, 1, 1, 1)
        self.attach(self.lbl_cur, 1, 1, 1, 1)
        self.attach(Gtk.Label(label="CPU:", xalign=0), 0, 2, 1, 1)
        self.attach(self.lbl_cpu, 1, 2, 1, 1)
        self.attach(Gtk.Separator(), 0, 3, 2, 1)

        self.radios = {}
        prev = None
        r = 4
        for key, label in PROFILES:
            rb = Gtk.RadioButton.new_with_label_from_widget(prev, label)
            prev = rb
            rb.connect("toggled", self.on_toggle, key)
            self.attach(rb, 0, r, 2, 1)
            self.radios[key] = rb
            r += 1
        self.msg = Gtk.Label(xalign=0)
        self.attach(self.msg, 0, r, 2, 1)

    def on_toggle(self, btn, key):
        if self._sync or not btn.get_active():
            return
        write_control(PROF_CONTROL, key)

    def refresh(self):
        st = read_status(PROF_STATUS)
        if not st:
            self.msg.set_markup("<span foreground='red'>Servicio clevo-profiled no activo</span>")
            return
        self.lbl_ac.set_text("Enchufado" if st.get("ac") == "1" else "Batería")
        self.lbl_cur.set_text(st.get("target", "?"))
        self.lbl_cpu.set_text("Turbo %s · máx %s MHz" % (st.get("turbo", "?"), st.get("cpumaxmhz", "?")))
        self.msg.set_text("")
        mode = st.get("mode", "auto")
        key = mode if mode in self.radios else "auto"
        self._sync = True
        self.radios[key].set_active(True)
        self._sync = False


class App(Gtk.Window):
    def __init__(self):
        super().__init__(title="XENIA Control")
        self.set_border_width(8)
        self.set_default_size(380, -1)
        nb = Gtk.Notebook()
        self.add(nb)
        self.fan = FanTab()
        self.perf = PerfTab()
        nb.append_page(self.fan, Gtk.Label(label="Ventiladores"))
        nb.append_page(self.perf, Gtk.Label(label="Rendimiento"))
        self.refresh()
        GLib.timeout_add_seconds(2, self.refresh)

    def refresh(self):
        self.fan.refresh()
        self.perf.refresh()
        return True


def main():
    w = App()
    w.connect("destroy", Gtk.main_quit)
    w.show_all()
    Gtk.main()


if __name__ == "__main__":
    main()
