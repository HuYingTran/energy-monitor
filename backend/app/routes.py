from flask import Blueprint, flash, g, jsonify, redirect, render_template, request, url_for

from app import influx_client, mqtt_service, tariff
from app.database import SessionLocal
from app.models import Alert, AlertRule, Device, RelayEvent, Site

bp = Blueprint("main", __name__)


def get_db():
    if "db" not in g:
        g.db = SessionLocal()
    return g.db


@bp.teardown_app_request
def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


@bp.route("/")
def index():
    return redirect(url_for("main.list_devices"))


@bp.route("/devices")
def list_devices():
    db = get_db()
    devices = db.query(Device).order_by(Device.name).all()
    sites = db.query(Site).order_by(Site.name).all()

    usage = {}
    for d in devices:
        kwh = influx_client.query_monthly_energy(d.id)
        usage[d.id] = {"kwh": kwh, "cost": tariff.estimate_cost(kwh)}

    return render_template("devices.html", devices=devices, sites=sites, usage=usage)


@bp.route("/devices", methods=["POST"])
def create_device():
    db = get_db()
    device_id = request.form["id"].strip()
    name = request.form.get("name", "").strip() or device_id
    site_id = request.form.get("site_id") or None

    if not device_id:
        flash("Thiếu mã thiết bị", "error")
    elif db.get(Device, device_id):
        flash("Thiết bị đã tồn tại", "error")
    else:
        db.add(Device(id=device_id, name=name, site_id=site_id))
        db.commit()
        flash(f"Đã thêm thiết bị {device_id}", "ok")
    return redirect(url_for("main.list_devices"))


@bp.route("/devices/<device_id>")
def device_detail(device_id):
    db = get_db()
    device = db.get(Device, device_id)
    if device is None:
        flash("Không tìm thấy thiết bị", "error")
        return redirect(url_for("main.list_devices"))

    latest = influx_client.query_latest(device_id)
    history = influx_client.query_history(device_id, range_start="-6h", every="5m")
    relay_events = (
        db.query(RelayEvent)
        .filter(RelayEvent.device_id == device_id)
        .order_by(RelayEvent.created_at.desc())
        .limit(20)
        .all()
    )
    return render_template(
        "device_detail.html",
        device=device,
        latest=latest,
        history=history,
        relay_events=relay_events,
    )


@bp.route("/devices/<device_id>/telemetry.json")
def device_telemetry_json(device_id):
    return jsonify(influx_client.query_latest(device_id))


@bp.route("/devices/<device_id>/relay", methods=["POST"])
def set_relay(device_id):
    db = get_db()
    device = db.get(Device, device_id)
    if device is None:
        flash("Không tìm thấy thiết bị", "error")
        return redirect(url_for("main.list_devices"))

    value = request.form.get("value") == "on"
    try:
        request_id = mqtt_service.publish_relay_command(device_id, value)
    except RuntimeError:
        flash("MQTT chưa kết nối, không gửi được lệnh", "error")
        return redirect(url_for("main.device_detail", device_id=device_id))

    db.add(RelayEvent(device_id=device_id, value=value, source="user", request_id=request_id))
    db.commit()
    flash(f"Đã gửi lệnh {'bật' if value else 'tắt'} relay, chờ thiết bị xác nhận", "ok")
    return redirect(url_for("main.device_detail", device_id=device_id))


@bp.route("/sites")
def list_sites():
    db = get_db()
    sites = db.query(Site).order_by(Site.name).all()
    return render_template("sites.html", sites=sites)


@bp.route("/sites", methods=["POST"])
def create_site():
    db = get_db()
    name = request.form.get("name", "").strip()
    description = request.form.get("description", "").strip() or None
    if not name:
        flash("Thiếu tên site", "error")
    else:
        db.add(Site(name=name, description=description))
        db.commit()
        flash(f"Đã thêm site {name}", "ok")
    return redirect(url_for("main.list_sites"))


@bp.route("/alerts")
def list_alerts():
    db = get_db()
    devices = db.query(Device).order_by(Device.name).all()
    rules = db.query(AlertRule).order_by(AlertRule.created_at.desc()).all()
    alerts = db.query(Alert).order_by(Alert.triggered_at.desc()).limit(50).all()
    return render_template("alerts.html", devices=devices, rules=rules, alerts=alerts)


@bp.route("/alert-rules", methods=["POST"])
def create_alert_rule():
    db = get_db()
    device_id = request.form.get("device_id")
    rule_type = request.form.get("rule_type")
    threshold = request.form.get("threshold", type=float)
    auto_cutoff = request.form.get("auto_cutoff") == "on"

    if not device_id or db.get(Device, device_id) is None:
        flash("Thiết bị không hợp lệ", "error")
    elif threshold is None:
        flash("Ngưỡng không hợp lệ", "error")
    else:
        db.add(
            AlertRule(
                device_id=device_id,
                rule_type=rule_type,
                threshold=threshold,
                auto_cutoff=auto_cutoff,
            )
        )
        db.commit()
        flash("Đã thêm ngưỡng cảnh báo", "ok")
    return redirect(url_for("main.list_alerts"))


@bp.route("/health")
def health():
    return jsonify({"status": "ok"})
