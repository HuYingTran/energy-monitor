"""Giả lập nhiều thiết bị ESP32-C3 + PZEM-004T publish MQTT.

Dùng để test end-to-end (ingestion -> InfluxDB -> API -> web) khi chưa có
phần cứng thật. Mỗi thiết bị publish telemetry định kỳ, phản hồi lệnh relay
qua cmd/ack, và publish status khi relay thay đổi.

Chạy: ./venv/bin/python scripts/simulate_devices.py (từ thư mục backend/)
"""

import json
import math
import os
import random
import sys
import time

import paho.mqtt.client as mqtt

MQTT_HOST = os.environ.get("MQTT_HOST", "localhost")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1883"))
PUBLISH_INTERVAL_S = 5

# Lưu trạng thái ra file để energy_kwh không bị nhảy số ngẫu nhiên mỗi lần
# restart script — giống bộ đếm điện năng non-volatile trên PZEM-004T thật,
# vẫn giữ nguyên giá trị sau khi thiết bị mất điện/khởi động lại.
STATE_FILE = os.path.join(os.path.dirname(__file__), ".sim_state.json")

DEVICES = [
    {"id": "sim-esp32-01", "name": "Máy lạnh phòng khách", "base_power": 850, "alarm_threshold": 900},
    {"id": "sim-esp32-02", "name": "Tủ lạnh bếp", "base_power": 150, "alarm_threshold": 900},
    {"id": "sim-esp32-03", "name": "Bơm nước sân thượng", "base_power": 400, "alarm_threshold": 900},
]


def _load_state() -> dict:
    try:
        with open(STATE_FILE) as f:
            saved = json.load(f)
    except (FileNotFoundError, ValueError):
        saved = {}
    return {
        d["id"]: saved.get(d["id"], {"relay": True, "energy_kwh": round(random.uniform(5, 50), 3)})
        for d in DEVICES
    }


def _save_state() -> None:
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)


state = _load_state()


def make_telemetry(device: dict, t: float) -> dict:
    relay_on = state[device["id"]]["relay"]
    if not relay_on:
        return {
            "ts": int(time.time()),
            "voltage": round(220 + random.uniform(-2, 2), 1),
            "current": 0.0,
            "power": 0.0,
            "energy": round(state[device["id"]]["energy_kwh"], 3),
            "frequency": 50.0,
            "power_factor": 0.0,
            "relay": False,
            "power_alarm": False,
        }

    noise = random.uniform(-0.05, 0.05)
    wobble = math.sin(t / 20) * 0.1
    power = max(0.0, device["base_power"] * (1 + noise + wobble))
    voltage = round(220 + random.uniform(-2, 2), 1)
    frequency = round(50.0 + random.uniform(-0.05, 0.05), 2)
    current = round(power / voltage, 3)
    state[device["id"]]["energy_kwh"] += power * PUBLISH_INTERVAL_S / 3600 / 1000

    return {
        "ts": int(time.time()),
        "voltage": voltage,
        "current": current,
        "power": round(power, 1),
        "energy": round(state[device["id"]]["energy_kwh"], 3),
        "frequency": frequency,
        "power_factor": round(random.uniform(0.92, 0.99), 2),
        "relay": True,
        "power_alarm": power > device["alarm_threshold"],
    }


def on_connect(client, userdata, flags, reason_code, properties=None):
    print(f"[sim] connected to {MQTT_HOST}:{MQTT_PORT} (rc={reason_code})")
    for device in DEVICES:
        client.subscribe(f"energy/{device['id']}/cmd")
        client.publish(
            f"energy/{device['id']}/status",
            json.dumps({"online": True, "relay": state[device["id"]]["relay"]}),
            retain=True,
        )


def on_message(client, userdata, msg):
    parts = msg.topic.split("/")
    if len(parts) < 3 or parts[0] != "energy" or parts[2] != "cmd":
        return
    device_id = parts[1]
    if device_id not in state:
        return
    try:
        payload = json.loads(msg.payload.decode())
    except ValueError:
        return

    if payload.get("action") == "relay_set":
        value = bool(payload["value"])
        state[device_id]["relay"] = value
        print(f"[sim] {device_id}: relay -> {value}")
        client.publish(
            f"energy/{device_id}/cmd/ack",
            json.dumps({"request_id": payload.get("request_id"), "value": value, "ok": True}),
        )
        client.publish(
            f"energy/{device_id}/status",
            json.dumps({"online": True, "relay": value}),
            retain=True,
        )


def main() -> None:
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(MQTT_HOST, MQTT_PORT, keepalive=30)
    client.loop_start()

    print(f"[sim] publishing telemetry mỗi {PUBLISH_INTERVAL_S}s cho {len(DEVICES)} thiết bị. Ctrl+C để dừng.")
    t = 0.0
    try:
        while True:
            for device in DEVICES:
                payload = make_telemetry(device, t)
                client.publish(f"energy/{device['id']}/telemetry", json.dumps(payload))
            _save_state()
            t += PUBLISH_INTERVAL_S
            time.sleep(PUBLISH_INTERVAL_S)
    except KeyboardInterrupt:
        pass
    finally:
        _save_state()
        client.loop_stop()
        client.disconnect()
        print("[sim] stopped")


if __name__ == "__main__":
    sys.exit(main() or 0)
