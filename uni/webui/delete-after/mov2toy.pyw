import tkinter as tk
from tkinter import ttk
import socket
import threading
import time
import cv2
import numpy as np
import mss
import pyautogui
import serial
import serial.tools.list_ports
import keyboard


class RegionSelector(tk.Toplevel):
    def __init__(self, master, callback):
        super().__init__(master)
        self.callback = callback
        self.start_x = None
        self.start_y = None
        self.rect_id = None

        self.canvas = tk.Canvas(self, cursor="cross", bg="gray")
        self.canvas.pack(fill="both", expand=True)

        self.attributes("-fullscreen", True)
        self.attributes("-alpha", 0.3)
        self.attributes("-topmost", True)

        self.bind("<Escape>", lambda e: self.destroy())
        self.canvas.bind("<ButtonPress-1>", self.on_start)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)

    def on_start(self, event):
        self.start_x = self.canvas.canvasx(event.x)
        self.start_y = self.canvas.canvasy(event.y)
        self.rect_id = self.canvas.create_rectangle(
            self.start_x, self.start_y, self.start_x, self.start_y,
            outline="red", width=2
        )

    def on_drag(self, event):
        cur_x = self.canvas.canvasx(event.x)
        cur_y = self.canvas.canvasy(event.y)
        self.canvas.coords(self.rect_id, self.start_x, self.start_y, cur_x, cur_y)

    def on_release(self, event):
        end_x = self.canvas.canvasx(event.x)
        end_y = self.canvas.canvasy(event.y)

        left = int(min(self.start_x, end_x))
        top = int(min(self.start_y, end_y))
        width = int(abs(end_x - self.start_x))
        height = int(abs(end_y - self.start_y))

        if width > 0 and height > 0:
            self.callback({"left": left, "top": top, "width": width, "height": height})
        self.destroy()


class mov2toy:
    def __init__(self, root):
        self.root = root
        self.root.title("mov2toy")

        self.running = False
        self.sock = None
        self.serial_conn = None
        self.capture_region = None

        # ===== Sensitivity params (read by capture thread) =====
        # Defaults maintain original behavior (approx. motion_value * 10, sending ~200ms)
        self.sens_threshold = 2.6      # dead-zone in motion_value units
        self.sens_gain = 10.0          # multiplication after threshold subtraction
        self.sens_smoothing = 0.95      # EMA alpha: 0 = without smoothing
        self.sens_period_s = 0.14      # period in seconds
        self.sens_max = 99.99          # max output (0..99.99)
        self.sens_gamma = 3.7          # response curve (1.0 = lineární)

        # UI update throttling
        self._last_ui_update_ts = 0.0

        # ===== GUI Layout =====
        self.select_region_button = ttk.Button(root, text="Select Region", command=self.select_region)
        self.select_region_button.grid(row=0, column=0, columnspan=2, pady=5)

        self.start_button = ttk.Button(root, text="Start", command=self.start_client)
        self.start_button.grid(row=1, column=0, pady=5)
        self.stop_button = ttk.Button(root, text="Stop", command=self.stop_client, state="disabled")
        self.stop_button.grid(row=1, column=1, pady=5)

        self.status_var = tk.StringVar(value="Status: Idle")
        self.status_label = ttk.Label(root, textvariable=self.status_var)
        self.status_label.grid(row=2, column=0, columnspan=2)

        ttk.Separator(root, orient='horizontal').grid(row=3, column=0, columnspan=2, sticky='ew', pady=5)
        settings_label = ttk.Label(root, text="Settings:", font=("Segoe UI", 10, "bold"))
        settings_label.grid(row=4, column=0, columnspan=2, sticky="w")

        # --- Serial settings
        self.serial_status = ttk.Label(root, text="Serial (Disconnected)")
        self.serial_status.grid(row=5, column=0, columnspan=2, sticky="w")

        self.serial_label = ttk.Label(root, text="Serial Port:")
        self.serial_label.grid(row=6, column=0, sticky="e")
        self.serial_combo = ttk.Combobox(root, values=self.get_serial_ports(), state="readonly")
        if self.serial_combo["values"]:
            self.serial_combo.current(0)
        self.serial_combo.grid(row=6, column=1, sticky="ew")

        self.refresh_button = ttk.Button(root, text="Refresh", command=self.refresh_serial_ports)
        self.refresh_button.grid(row=7, column=0, sticky="ew")
        self.connect_serial_button = ttk.Button(root, text="Connect Serial", command=self.toggle_serial_connection)
        self.connect_serial_button.grid(row=7, column=1, sticky="ew")

        # --- TCP settings
        self.tcp_status = ttk.Label(root, text="TCP (Disconnected)")
        self.tcp_status.grid(row=8, column=0, columnspan=2, sticky="w")

        self.ip_label = ttk.Label(root, text="IP/Host:")
        self.ip_label.grid(row=9, column=0, sticky="e")
        self.ip_entry = ttk.Entry(root)
        self.ip_entry.insert(0, "127.0.0.1")
        self.ip_entry.grid(row=9, column=1, sticky="ew")

        self.port_label = ttk.Label(root, text="Port:")
        self.port_label.grid(row=10, column=0, sticky="e")
        self.port_entry = ttk.Entry(root)
        self.port_entry.insert(0, "12347")
        self.port_entry.grid(row=10, column=1, sticky="ew")

        self.connect_tcp_button = ttk.Button(root, text="Connect TCP", command=self.toggle_tcp_connection)
        self.connect_tcp_button.grid(row=11, column=0, columnspan=2, pady=5, sticky="ew")

        # --- Channel selection
        ttk.Separator(root, orient='horizontal').grid(row=12, column=0, columnspan=2, sticky='ew', pady=5)
        self.channel_label = ttk.Label(root, text="Channel:")
        self.channel_label.grid(row=13, column=0, sticky="e")

        self.channel_info = {
            "L0": ("Up/Down", ["stroke", "L0", "up", "raw"]),
            "L1": ("Forward/Backward", ["surge", "L1", "forward"]),
            "L2": ("Left/Right", ["sway", "L2", "left"]),
            "R0": ("Twist", ["twist", "R0", "yaw"]),
            "R1": ("Roll", ["roll", "R1"]),
            "R2": ("Pitch", ["pitch", "R2"]),
            "V0": ("Vibrate", ["vib", "V0"]),
            "V1": ("Pump", ["pump", "VI"]),  # dle tvé tabulky
            "A0": ("Valve", ["valve", "A0"]),
            "A1": ("Suction", ["suck", "A1"]),
            "A2": ("Lube", ["lube", "A2"]),
        }
        self._channel_order = ["L0", "L1", "L2", "R0", "R1", "R2", "V0", "V1", "A0", "A1", "A2"]
        channel_display_values = [f"{code} — {self.channel_info[code][0]}" for code in self._channel_order]

        self.channel_combo = ttk.Combobox(root, values=channel_display_values, state="readonly")
        self.channel_combo.set(f"V0 — {self.channel_info['V0'][0]}")
        self.channel_combo.grid(row=13, column=1, sticky="ew")

        # --- Sensitivity sliders
        ttk.Separator(root, orient='horizontal').grid(row=14, column=0, columnspan=2, sticky='ew', pady=5)
        sens_label = ttk.Label(root, text="Sensitivity:", font=("Segoe UI", 10, "bold"))
        sens_label.grid(row=15, column=0, columnspan=2, sticky="w")

        # Threshold
        self.thr_var = tk.DoubleVar(value=self.sens_threshold)
        ttk.Label(root, text="Threshold:").grid(row=16, column=0, sticky="e")
        self.thr_scale = ttk.Scale(
            root, from_=0.0, to=5.0, orient="horizontal",
            variable=self.thr_var, command=lambda _v: self._on_thr_change()
        )
        self.thr_scale.grid(row=16, column=1, sticky="ew")
        self.thr_val_label = ttk.Label(root, text=f"{self.sens_threshold:.2f}")
        self.thr_val_label.grid(row=16, column=2, padx=(8, 0), sticky="w")

        # Gain
        self.gain_var = tk.DoubleVar(value=self.sens_gain)
        ttk.Label(root, text="Gain:").grid(row=17, column=0, sticky="e")
        self.gain_scale = ttk.Scale(
            root, from_=0.0, to=30.0, orient="horizontal",
            variable=self.gain_var, command=lambda _v: self._on_gain_change()
        )
        self.gain_scale.grid(row=17, column=1, sticky="ew")
        self.gain_val_label = ttk.Label(root, text=f"{self.sens_gain:.2f}")
        self.gain_val_label.grid(row=17, column=2, padx=(8, 0), sticky="w")

        # Smoothing
        self.smooth_var = tk.DoubleVar(value=self.sens_smoothing)
        ttk.Label(root, text="Smoothing:").grid(row=18, column=0, sticky="e")
        self.smooth_scale = ttk.Scale(
            root, from_=0.0, to=1.0, orient="horizontal",
            variable=self.smooth_var, command=lambda _v: self._on_smooth_change()
        )
        self.smooth_scale.grid(row=18, column=1, sticky="ew")
        self.smooth_val_label = ttk.Label(root, text=f"{self.sens_smoothing:.2f}")
        self.smooth_val_label.grid(row=18, column=2, padx=(8, 0), sticky="w")

        # Update interval (ms)
        self.period_ms_var = tk.DoubleVar(value=self.sens_period_s * 1000.0)
        ttk.Label(root, text="Update (ms):").grid(row=19, column=0, sticky="e")
        self.period_scale = ttk.Scale(
            root, from_=50, to=500, orient="horizontal",
            variable=self.period_ms_var, command=lambda _v: self._on_period_change()
        )
        self.period_scale.grid(row=19, column=1, sticky="ew")
        self.period_val_label = ttk.Label(root, text=f"{int(self.sens_period_s * 1000)}")
        self.period_val_label.grid(row=19, column=2, padx=(8, 0), sticky="w")

        # Max output
        self.max_var = tk.DoubleVar(value=self.sens_max)
        ttk.Label(root, text="Max:").grid(row=20, column=0, sticky="e")
        self.max_scale = ttk.Scale(
            root, from_=0.0, to=99.99, orient="horizontal",
            variable=self.max_var, command=lambda _v: self._on_max_change()
        )
        self.max_scale.grid(row=20, column=1, sticky="ew")
        self.max_val_label = ttk.Label(root, text=f"{self.sens_max:.2f}")
        self.max_val_label.grid(row=20, column=2, padx=(8, 0), sticky="w")

        # Response curve (gamma)
        self.gamma_var = tk.DoubleVar(value=self.sens_gamma)
        ttk.Label(root, text="Curve (γ):").grid(row=21, column=0, sticky="e")
        self.gamma_scale = ttk.Scale(
            root, from_=0.20, to=5.00, orient="horizontal",
            variable=self.gamma_var, command=lambda _v: self._on_gamma_change()
        )
        self.gamma_scale.grid(row=21, column=1, sticky="ew")
        self.gamma_val_label = ttk.Label(root, text=f"{self.sens_gamma:.2f}")
        self.gamma_val_label.grid(row=21, column=2, padx=(8, 0), sticky="w")

        # --- Live output indicator
        ttk.Separator(root, orient='horizontal').grid(row=22, column=0, columnspan=2, sticky='ew', pady=5)
        live_label = ttk.Label(root, text="Live output:", font=("Segoe UI", 10, "bold"))
        live_label.grid(row=23, column=0, columnspan=2, sticky="w")

        self.live_out_var = tk.DoubleVar(value=0.0)
        self.live_out_bar = ttk.Progressbar(
            root, orient="horizontal", mode="determinate",
            maximum=99.99, variable=self.live_out_var
        )
        self.live_out_bar.grid(row=24, column=0, columnspan=2, sticky="ew", pady=(0, 3))

        self.live_out_text = ttk.Label(root, text="0.00")
        self.live_out_text.grid(row=24, column=2, padx=(8, 0), sticky="w")

        # Layout: ať se entry/slider/progressbar roztahují
        root.grid_columnconfigure(1, weight=1)

        # Global hotkey for Select Region
        keyboard.add_hotkey('f10', lambda: self.select_region())

    # ===== Slider callbacks =====
    def _on_thr_change(self):
        self.sens_threshold = float(self.thr_var.get())
        self.thr_val_label.config(text=f"{self.sens_threshold:.2f}")

    def _on_gain_change(self):
        self.sens_gain = float(self.gain_var.get())
        self.gain_val_label.config(text=f"{self.sens_gain:.2f}")

    def _on_smooth_change(self):
        self.sens_smoothing = float(self.smooth_var.get())
        self.smooth_val_label.config(text=f"{self.sens_smoothing:.2f}")

    def _on_period_change(self):
        ms = float(self.period_ms_var.get())
        self.sens_period_s = max(0.01, ms / 1000.0)
        self.period_val_label.config(text=f"{int(ms)}")

    def _on_max_change(self):
        self.sens_max = float(self.max_var.get())
        self.max_val_label.config(text=f"{self.sens_max:.2f}")

    def _on_gamma_change(self):
        self.sens_gamma = float(self.gamma_var.get())
        self.gamma_val_label.config(text=f"{self.sens_gamma:.2f}")

    # ===== Thread-safe UI update =====
    def _post_live_value(self, value: float):
        """Volat z worker threadu: bezpečně aktualizuje progress bar a číslo."""
        now = time.time()
        if now - self._last_ui_update_ts < (1.0 / 30.0):  # ~30 FPS max
            return
        self._last_ui_update_ts = now

        def _update():
            try:
                v = max(0.0, min(99.99, float(value)))
                self.live_out_var.set(v)
                self.live_out_text.config(text=f"{v:.2f}")
            except tk.TclError:
                pass

        self.root.after(0, _update)

    # ===== Helpers =====
    def _selected_channel_code(self) -> str:
        sel = self.channel_combo.get().strip()
        if not sel:
            return "V0"
        code = sel.split(" ")[0].strip()
        return code if code in self.channel_info else "V0"

    def _encode_value_frame(self, channel_code: str, value_0_100: float) -> str:
        clamped = max(0.0, min(99.99, float(value_0_100)))
        value_str = f"{int(round(clamped * 100)):04d}"
        return f"{channel_code}{value_str}\n"

    def send_zero_value(self):
        self._post_live_value(0.0)
        channel = self._selected_channel_code()
        zero_frame = self._encode_value_frame(channel, 0.0).encode()
        if self.sock:
            try:
                self.sock.sendall(zero_frame)
            except:
                pass
        if self.serial_conn and self.serial_conn.is_open:
            try:
                self.serial_conn.write(zero_frame)
            except:
                pass

    def get_serial_ports(self):
        return [port.device for port in serial.tools.list_ports.comports()]

    def refresh_serial_ports(self):
        self.serial_combo.set("")
        ports = self.get_serial_ports()
        self.serial_combo["values"] = ports
        if ports:
            self.serial_combo.current(0)
            self.connect_serial_button.config(state="normal")
        else:
            self.connect_serial_button.config(state="disabled")

    def toggle_serial_connection(self):
        if self.serial_conn and self.serial_conn.is_open:
            self.serial_conn.close()
            self.serial_status.config(text="Serial (Disconnected)")
            self.connect_serial_button.config(text="Connect Serial")
        else:
            port = self.serial_combo.get()
            try:
                self.serial_conn = serial.Serial(port, baudrate=115200, timeout=1)
                self.serial_status.config(text=f"Serial (Connected: {port})")
                self.connect_serial_button.config(text="Disconnect Serial")
            except Exception as e:
                self.serial_status.config(text=f"Serial (Error: {e})")

    def select_region(self):
        if self.running:
            self.send_zero_value()
            self.running = False
            self.start_button.config(state="normal")
            self.stop_button.config(state="disabled")
            self.status_var.set("Paused for region update")
        RegionSelector(self.root, self.set_capture_region)

    def set_capture_region(self, region):
        self.capture_region = region
        self.start_client()

    def toggle_tcp_connection(self):
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None
            self.tcp_status.config(text="TCP (Disconnected)")
            self.connect_tcp_button.config(text="Connect TCP")
        else:
            host = self.ip_entry.get()
            port = int(self.port_entry.get())

            def try_connect():
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                try:
                    sock.connect((host, port))
                    self.sock = sock
                    self.tcp_status.config(text=f"TCP (Connected: {host}:{port})")
                    self.connect_tcp_button.config(text="Disconnect TCP")
                except Exception:
                    try:
                        sock.close()
                    except Exception:
                        pass

            threading.Thread(target=try_connect, daemon=True).start()

    def start_client(self):
        if self.running:
            return
        self.running = True
        self.start_button.config(state="disabled")
        self.stop_button.config(state="normal")
        threading.Thread(target=self.capture_loop, daemon=True).start()

    def stop_client(self):
        self.send_zero_value()
        self.running = False
        self.start_button.config(state="normal")
        self.stop_button.config(state="disabled")
        self.status_var.set("Status: Stopped")

    def capture_loop(self):
        cycle_times = []
        with mss.mss() as sct:
            monitor = self.capture_region if self.capture_region else sct.monitors[1]
            prev_gray = None
            prev_out = 0.0  # pro EMA

            while self.running:
                start_time = time.time()
                img = np.array(sct.grab(monitor))
                gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

                if prev_gray is not None:
                    flow = cv2.calcOpticalFlowFarneback(
                        prev_gray, gray, None,
                        pyr_scale=0.5, levels=3, winsize=15,
                        iterations=3, poly_n=5, poly_sigma=1.2, flags=0
                    )

                    # divergence
                    div = np.gradient(flow[..., 0], axis=0) + np.gradient(flow[..., 1], axis=1)
                    y, x = np.unravel_index(np.argmax(np.abs(div)), div.shape)
                    motion_value = abs(div[y, x])

                    # --- Apply sensitivity params ---
                    thr = self.sens_threshold
                    gain = self.sens_gain
                    alpha = self.sens_smoothing
                    period = self.sens_period_s
                    vmax = self.sens_max
                    gamma = self.sens_gamma

                    mv = motion_value - thr
                    if mv < 0.0:
                        mv = 0.0

                    # lineární základ
                    raw_value = mv * gain

                    # clamp 0..min(vmax, 99.99)
                    cap = min(99.99, max(0.0, float(vmax)))
                    value = max(0.0, min(cap, raw_value))

                    # křivka odezvy (gamma) na normalizovanou hodnotu
                    if cap > 0.0 and abs(gamma - 1.0) > 1e-6:
                        n = value / cap  # 0..1
                        if n < 0.0:
                            n = 0.0
                        elif n > 1.0:
                            n = 1.0
                        value = (n ** gamma) * cap

                    # EMA smoothing
                    if alpha > 0.0:
                        out_value = (alpha * value) + ((1.0 - alpha) * prev_out)
                    else:
                        out_value = value
                    prev_out = out_value

                    if not self.running:
                        break

                    # Live indicator
                    self._post_live_value(out_value)

                    # Send
                    channel = self._selected_channel_code()
                    encoded_value = self._encode_value_frame(channel, out_value)

                    try:
                        if self.sock:
                            self.sock.sendall(encoded_value.encode())
                        if self.serial_conn and self.serial_conn.is_open:
                            self.serial_conn.write(encoded_value.encode())
                    except Exception:
                        self.stop_client()
                        break

                    # cíluj periodu z UI
                    delta = time.time() - start_time
                    if delta < period:
                        time.sleep(period - delta)

                    elapsed = (time.time() - start_time) * 1000
                    cycle_times.append(elapsed)
                    if len(cycle_times) > 10:
                        cycle_times.pop(0)
                    avg_time = sum(cycle_times) / len(cycle_times) if cycle_times else 0
                    if avg_time > 0:
                        freq = int(60000 / avg_time)
                        self.status_var.set(f"Status: Running | {freq} cpm")

                prev_gray = gray


def main():
    root = tk.Tk()
    app = mov2toy(root)

    def on_close():
        try:
            keyboard.unhook_all_hotkeys()
        except Exception:
            pass
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    root.mainloop()


if __name__ == '__main__':
    main()