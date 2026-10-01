import json
import uuid
from datetime import datetime, timezone

import paho.mqtt.client as mqtt

from app import influx_client
from app.config import settings
from app.database import SessionLocal
from app.models import Device, RelayEvent

_client: mqtt.Client | None = None


def _topic_device_id(topic: str) -> str | None:
    parts = topic.split("/")
    if len(parts) >= 2 and parts[0] == "energy":
        return parts[1]
    return None


def _get_or_create_device(db, device_id: str) -> Device:
    device = db.get(Device, device_id)
    if device is None:
        device = Device(id=device_id, name=device_id)
        db.add(device)
    return device


def _handle_telemetry(device_id: str, payload: dict) -> None:
    db = SessionLocal()
    try:
        device = _get_or_create_device(db, device_id)
        device.online = True
        device.last_seen = datetime.now(timezone.utc)
        if "relay" in payload:
            device.relay_state = bool(payload["relay"])
        site_id = device.site_id
        db.commit()
    finally:
        db.close()

    influx_client.write_telemetry(device_id, site_id, payload)


def _handle_status(device_id: str, payload: dict) -> None:
    db = SessionLocal()
    try:
        device = _get_or_create_device(db, device_id)
        device.online = bool(payload.get("online", True))
        if "relay" in payload:
            device.relay_state = bool(payload["relay"])
        device.last_seen = datetime.now(timezone.utc)
        db.commit()
    finally:
        db.close()


def _handle_cmd_ack(device_id: str, payload: dict) -> None:
    request_id = payload.get("request_id")
    if not request_id:
        return
    db = SessionLocal()
    try:
        event = db.query(RelayEvent).filter_by(request_id=request_id).first()
        if event:
            event.acked = True
            device = db.get(Device, device_id)
            if device is not None and "value" in payload:
                device.relay_state = bool(payload["value"])
            db.commit()
    finally:
        db.close()


def _on_connect(client, userdata, flags, reason_code, properties=None):
    client.subscribe("energy/+/telemetry")
    client.subscribe("energy/+/status")
    client.subscribe("energy/+/cmd/ack")


def _on_message(client, userdata, msg):
    device_id = _topic_device_id(msg.topic)
    if device_id is None:
        return
    try:
        payload = json.loads(msg.payload.decode())
    except (ValueError, UnicodeDecodeError):
        return

    if msg.topic.endswith("/telemetry"):
        _handle_telemetry(device_id, payload)
    elif msg.topic.endswith("/status"):
        _handle_status(device_id, payload)
    elif msg.topic.endswith("/cmd/ack"):
        _handle_cmd_ack(device_id, payload)


def start() -> None:
    global _client
    if _client is not None:
        return
    _client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    _client.on_connect = _on_connect
    _client.on_message = _on_message
    _client.connect(settings.mqtt_host, settings.mqtt_port, keepalive=30)
    _client.loop_start()


def stop() -> None:
    if _client:
        _client.loop_stop()
        _client.disconnect()


def publish_relay_command(device_id: str, value: bool) -> str:
    if _client is None:
        raise RuntimeError("MQTT client chưa được khởi tạo")
    request_id = str(uuid.uuid4())
    payload = {"action": "relay_set", "value": value, "request_id": request_id}
    _client.publish(f"energy/{device_id}/cmd", json.dumps(payload), qos=1)
    return request_id
