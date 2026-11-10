from flask import Flask, render_template, jsonify, request, send_file
import serial
import serial.tools.list_ports
import threading
import time
import csv
from pathlib import Path
from datetime import datetime

BASE = Path(__file__).resolve().parent
LOG_DIR = BASE / "session_logs"
LOG_DIR.mkdir(exist_ok=True)

app = Flask(__name__)

BAUD = 115200

# ---------------- LIVE-DEMO BASELINE ----------------
# These are startup/demo defaults only.
# The first completed rep automatically anchors the baseline to the
# actual live signal unless you manually apply a baseline in the UI.
DEFAULT_BASELINE_EMG = 300.0
DEFAULT_BASELINE_REP_TIME = 4.0
DEFAULT_BASELINE_TERMINAL_DECEL = 1200.0

FATIGUE_RATIO = 1.20
TIME_TOLERANCE = 0.35
MIN_DECEL_RATIO = 0.60
# ----------------------------------------------------

print("\nAvailable serial ports")
print("----------------------")
for p in serial.tools.list_ports.comports():
    print(f"{p.device:6}  {p.description}")

ARDUINO_PORT = input("\nArduino / EMG port: ").strip().upper()
ESP32_PORT = input("ESP32 / MPU6050 port: ").strip().upper()

session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
csv_path = LOG_DIR / f"session_{session_id}.csv"

CSV_FIELDS = [
    "timestamp",
    "rep",
    "rep_time_s",
    "mean_emg",
    "peak_emg",
    "normalized_emg_pct",
    "terminal_decel_proxy_dps2",
    "tempo_deviation_pct",
    "current_load_kg",
    "fatigue_status",
    "control_status",
    "baseline_decision",
    "progression_status"
]

with open(csv_path, "w", newline="", encoding="utf-8") as f:
    csv.DictWriter(f, fieldnames=CSV_FIELDS).writeheader()

state_lock = threading.Lock()

state = {
    "emg_raw": 0,
    "emg_filtered": 0,
    "muscle_state": "WAITING",
    "gx": 0.0,
    "gy": 0.0,
    "gz": 0.0,
    "wrist_state": "WAITING",
    "reps": 0,
    "last_rep_time_s": 0.0,
    "last_mean_emg": 0.0,
    "last_peak_emg": 0.0,
    "last_normalized_emg_pct": 100.0,
    "last_terminal_decel": 0.0,
    "last_tempo_deviation_pct": 0.0,
    "arduino_connected": False,
    "esp32_connected": False,
    "current_load_kg": 0.0,
    "fatigue_status": "NO",
    "control_status": "BASELINE ACTIVE",
    "baseline_decision": "ADMIT",
    "progression_status": "DEMO BASELINE ACTIVE",
    "exercise_guidance": "Complete a repetition. Rep 1 will anchor the live demo baseline.",
    "csv_file": csv_path.name,
    "baseline_emg": DEFAULT_BASELINE_EMG,
    "baseline_rep_time": DEFAULT_BASELINE_REP_TIME,
    "baseline_terminal_decel": DEFAULT_BASELINE_TERMINAL_DECEL,
    "baseline_source": "STARTUP DEMO DEFAULT",
    "auto_anchor_first_rep": True
}

rep_rows = []
rep_emg_samples = []
rep_gyro_samples = []

previous_rep = 0
rep_started = False


def terminal_decel_proxy(samples):
    if len(samples) < 3:
        return 0.0

    derivatives = []

    for i in range(1, len(samples)):
        t0, y0 = samples[i - 1]
        t1, y1 = samples[i]
        dt = t1 - t0

        if dt > 0:
            derivatives.append(abs((y1 - y0) / dt))

    if not derivatives:
        return 0.0

    tail = derivatives[-6:]
    return sum(tail) / len(tail)


def evaluate_rep(rep_time_s, mean_emg, terminal_decel):
    baseline_emg = max(state["baseline_emg"], 1.0)
    baseline_time = max(state["baseline_rep_time"], 0.1)
    baseline_decel = max(state["baseline_terminal_decel"], 1.0)

    norm_pct = (mean_emg / baseline_emg) * 100.0
    tempo_dev_pct = abs(rep_time_s - baseline_time) / baseline_time * 100.0

    fatigue = "TREND" if mean_emg >= baseline_emg * FATIGUE_RATIO else "NO"

    time_good = abs(rep_time_s - baseline_time) / baseline_time <= TIME_TOLERANCE
    decel_good = terminal_decel <= 0 or terminal_decel >= baseline_decel * MIN_DECEL_RATIO

    control = "GOOD" if time_good and decel_good else "DEGRADED"

    if fatigue == "TREND" and control == "GOOD":
        decision = "WITHHOLD"
    else:
        decision = "ADMIT"

    return norm_pct, tempo_dev_pct, fatigue, control, decision


def progression_for(fatigue, control, load_kg):
    recent = rep_rows[-3:]

    if control == "DEGRADED":
        return (
            "REVIEW / REDUCE LOAD",
            "Movement control departed from the demo baseline. Restore controlled tempo before progressing."
        )

    if fatigue == "TREND" and control == "GOOD":
        return (
            "MAINTAIN LOAD",
            "EMG demand increased while movement control stayed preserved. Maintain the current load and monitor the next rep."
        )

    if len(recent) >= 3 and all(
        r["control_status"] == "GOOD" and r["fatigue_status"] == "NO"
        for r in recent
    ):
        return (
            "PROGRESSION CANDIDATE",
            "Recent reps are controlled without a fatigue trend. For the demo, this is a candidate for a small supervised progression."
        )

    if load_kg > 0:
        return (
            f"MAINTAIN {load_kg:g} kg",
            "Continue at the current load while maintaining consistent rep timing and control."
        )

    return (
        "MAINTAIN CURRENT LOAD",
        "Continue controlled repetitions and watch the rep-level trend."
    )


def save_row(row):
    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writerow({
            "timestamp": row["timestamp"],
            "rep": row["rep"],
            "rep_time_s": f'{row["rep_time_s"]:.3f}',
            "mean_emg": f'{row["mean_emg"]:.2f}',
            "peak_emg": f'{row["peak_emg"]:.2f}',
            "normalized_emg_pct": f'{row["normalized_emg_pct"]:.2f}',
            "terminal_decel_proxy_dps2": f'{row["terminal_decel_proxy_dps2"]:.2f}',
            "tempo_deviation_pct": f'{row["tempo_deviation_pct"]:.2f}',
            "current_load_kg": f'{row["current_load_kg"]:.2f}',
            "fatigue_status": row["fatigue_status"],
            "control_status": row["control_status"],
            "baseline_decision": row["baseline_decision"],
            "progression_status": row["progression_status"]
        })


def read_arduino():
    global rep_emg_samples

    while True:
        try:
            print(f"Opening Arduino on {ARDUINO_PORT}...")
            ser = serial.Serial(ARDUINO_PORT, BAUD, timeout=1)
            time.sleep(2)
            print("Arduino connected.")

            while True:
                line = ser.readline().decode(errors="ignore").strip()

                if not line:
                    continue

                p = line.split(",")

                try:
                    raw = int(float(p[0]))
                    filtered = int(float(p[1])) if len(p) >= 2 else raw
                except (ValueError, IndexError):
                    continue

                with state_lock:
                    state["emg_raw"] = raw
                    state["emg_filtered"] = filtered
                    state["muscle_state"] = "ACTIVE" if filtered >= 150 else "RELAXED"
                    state["arduino_connected"] = True

                    if rep_started:
                        rep_emg_samples.append(filtered)

        except Exception as e:
            print("Arduino error:", e)

            with state_lock:
                state["arduino_connected"] = False

            time.sleep(2)


def read_esp32():
    global previous_rep, rep_started, rep_emg_samples, rep_gyro_samples

    while True:
        try:
            print(f"Opening ESP32 on {ESP32_PORT}...")
            ser = serial.Serial(ESP32_PORT, BAUD, timeout=1)
            time.sleep(2)
            print("ESP32 connected.")

            while True:
                line = ser.readline().decode(errors="ignore").strip()

                if not line:
                    continue

                p = line.split(",")

                if len(p) != 6:
                    continue

                try:
                    gx = float(p[0])
                    gy = float(p[1])
                    gz = float(p[2])
                    wrist_state = p[3]
                    reps = int(p[4])
                    rep_time_s = float(p[5])
                except ValueError:
                    continue

                now = time.monotonic()

                with state_lock:
                    state["gx"] = gx
                    state["gy"] = gy
                    state["gz"] = gz
                    state["wrist_state"] = wrist_state
                    state["reps"] = reps
                    state["last_rep_time_s"] = rep_time_s
                    state["esp32_connected"] = True

                    if wrist_state == "WRIST UP" and not rep_started:
                        rep_started = True
                        rep_emg_samples = []
                        rep_gyro_samples = []

                    if rep_started:
                        rep_gyro_samples.append((now, gy))

                    if reps > previous_rep:
                        samples = rep_emg_samples[:] if rep_emg_samples else [state["emg_filtered"]]

                        mean_emg = sum(samples) / len(samples)
                        peak_emg = max(samples)
                        terminal_decel = terminal_decel_proxy(rep_gyro_samples)

                        # For the live faculty demo, rep 1 anchors the assumed baseline
                        # to the actual current electrode placement / signal scale.
                        if state["auto_anchor_first_rep"] and previous_rep == 0:
                            state["baseline_emg"] = max(mean_emg, 1.0)
                            state["baseline_rep_time"] = max(rep_time_s, 0.1)

                            if terminal_decel > 0:
                                state["baseline_terminal_decel"] = terminal_decel

                            state["baseline_source"] = "REP 1 LIVE DEMO ANCHOR"
                            state["auto_anchor_first_rep"] = False

                        (
                            norm_pct,
                            tempo_dev_pct,
                            fatigue,
                            control,
                            decision
                        ) = evaluate_rep(
                            rep_time_s,
                            mean_emg,
                            terminal_decel
                        )

                        # The anchor rep itself is the reference.
                        if previous_rep == 0 and state["baseline_source"] == "REP 1 LIVE DEMO ANCHOR":
                            norm_pct = 100.0
                            tempo_dev_pct = 0.0
                            fatigue = "NO"
                            control = "GOOD"
                            decision = "ADMIT"

                        load = float(state["current_load_kg"])

                        progression, guidance = progression_for(
                            fatigue,
                            control,
                            load
                        )

                        row = {
                            "timestamp": datetime.now().isoformat(timespec="seconds"),
                            "rep": reps,
                            "rep_time_s": rep_time_s,
                            "mean_emg": mean_emg,
                            "peak_emg": peak_emg,
                            "normalized_emg_pct": norm_pct,
                            "terminal_decel_proxy_dps2": terminal_decel,
                            "tempo_deviation_pct": tempo_dev_pct,
                            "current_load_kg": load,
                            "fatigue_status": fatigue,
                            "control_status": control,
                            "baseline_decision": decision,
                            "progression_status": progression
                        }

                        rep_rows.append(row)
                        save_row(row)

                        state["last_mean_emg"] = mean_emg
                        state["last_peak_emg"] = peak_emg
                        state["last_normalized_emg_pct"] = norm_pct
                        state["last_terminal_decel"] = terminal_decel
                        state["last_tempo_deviation_pct"] = tempo_dev_pct
                        state["fatigue_status"] = fatigue
                        state["control_status"] = control
                        state["baseline_decision"] = decision
                        state["progression_status"] = progression
                        state["exercise_guidance"] = guidance

                        previous_rep = reps
                        rep_started = False
                        rep_emg_samples = []
                        rep_gyro_samples = []

        except Exception as e:
            print("ESP32 error:", e)

            with state_lock:
                state["esp32_connected"] = False

            time.sleep(2)


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/api/state")
def api_state():
    with state_lock:
        payload = dict(state)
        payload["rep_rows"] = rep_rows[-25:]
        payload["admitted_count"] = sum(
            1 for r in rep_rows if r["baseline_decision"] == "ADMIT"
        )
        payload["withheld_count"] = sum(
            1 for r in rep_rows if r["baseline_decision"] == "WITHHOLD"
        )

    return jsonify(payload)


@app.route("/api/load", methods=["POST"])
def api_load():
    body = request.get_json(silent=True) or {}

    try:
        load = max(0.0, float(body.get("load_kg", 0)))
    except (TypeError, ValueError):
        return jsonify({"ok": False}), 400

    with state_lock:
        state["current_load_kg"] = load

    return jsonify({"ok": True})


@app.route("/api/baseline", methods=["POST"])
def api_baseline():
    body = request.get_json(silent=True) or {}

    try:
        baseline_emg = max(1.0, float(body.get("baseline_emg", state["baseline_emg"])))
        baseline_time = max(0.1, float(body.get("baseline_rep_time", state["baseline_rep_time"])))
    except (TypeError, ValueError):
        return jsonify({"ok": False}), 400

    with state_lock:
        state["baseline_emg"] = baseline_emg
        state["baseline_rep_time"] = baseline_time
        state["baseline_source"] = "MANUAL DEMO BASELINE"
        state["auto_anchor_first_rep"] = False

    return jsonify({"ok": True})


@app.route("/download-csv")
def download_csv():
    return send_file(csv_path, as_attachment=True, download_name=csv_path.name)


if __name__ == "__main__":
    threading.Thread(target=read_arduino, daemon=True).start()
    threading.Thread(target=read_esp32, daemon=True).start()

    print(f"\nCSV log: {csv_path}")
    print("Live-demo mode: baseline is available immediately.")
    print("Rep 1 automatically anchors baseline unless you manually set it.")
    print("Open http://127.0.0.1:5000\n")

    app.run(
        host="127.0.0.1",
        port=5000,
        debug=False,
        use_reloader=False
    )