from flask import Flask, render_template, jsonify
import serial
import threading
import time

ARDUINO_PORT = "COM16"
ESP32_PORT = "COM9"
BAUD = 115200

app = Flask(__name__)

data = {
    "emg_raw": 0,
    "emg_filtered": 0,
    "muscle_state": "WAITING",
    "gx": 0.0,
    "gy": 0.0,
    "gz": 0.0,
    "wrist_state": "WAITING",
    "reps": 0,
    "arduino_connected": False,
    "esp32_connected": False,
    "arduino_time": 0,
    "esp32_time": 0
}

lock = threading.Lock()


def read_arduino():
    while True:
        try:
            ser = serial.Serial(ARDUINO_PORT, BAUD, timeout=1)
            time.sleep(2)

            while True:
                line = ser.readline().decode(errors="ignore").strip()

                if not line:
                    continue

                parts = line.split(",")

                try:
                    if len(parts) >= 2:
                        raw = int(float(parts[0]))
                        filtered = int(float(parts[1]))
                    elif len(parts) == 1:
                        raw = int(float(parts[0]))
                        filtered = raw
                    else:
                        continue

                    state = "ACTIVE" if filtered >= 150 else "RELAXED"

                    with lock:
                        data["emg_raw"] = raw
                        data["emg_filtered"] = filtered
                        data["muscle_state"] = state
                        data["arduino_connected"] = True
                        data["arduino_time"] = time.time()

                except ValueError:
                    pass

        except Exception as e:
            with lock:
                data["arduino_connected"] = False

            print("Arduino:", e)
            time.sleep(2)


def read_esp32():
    while True:
        try:
            ser = serial.Serial(ESP32_PORT, BAUD, timeout=1)
            time.sleep(2)

            while True:
                line = ser.readline().decode(errors="ignore").strip()

                if not line:
                    continue

                parts = line.split(",")

                if len(parts) != 5:
                    continue

                try:
                    gx = float(parts[0])
                    gy = float(parts[1])
                    gz = float(parts[2])
                    state = parts[3]
                    reps = int(parts[4])

                    with lock:
                        data["gx"] = gx
                        data["gy"] = gy
                        data["gz"] = gz
                        data["wrist_state"] = state
                        data["reps"] = reps
                        data["esp32_connected"] = True
                        data["esp32_time"] = time.time()

                except ValueError:
                    pass

        except Exception as e:
            with lock:
                data["esp32_connected"] = False

            print("ESP32:", e)
            time.sleep(2)


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/data")
def get_data():
    with lock:
        result = data.copy()

    now = time.time()

    if now - result["arduino_time"] > 2:
        result["arduino_connected"] = False

    if now - result["esp32_time"] > 2:
        result["esp32_connected"] = False

    return jsonify(result)


if __name__ == "__main__":
    threading.Thread(target=read_arduino, daemon=True).start()
    threading.Thread(target=read_esp32, daemon=True).start()

    app.run(
        host="127.0.0.1",
        port=5000,
        debug=False,
        use_reloader=False
    )