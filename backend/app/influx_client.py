from datetime import datetime, timezone

from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS

from app.config import settings

_client = InfluxDBClient(url=settings.influx_url, token=settings.influx_token, org=settings.influx_org)
_write_api = _client.write_api(write_options=SYNCHRONOUS)
_query_api = _client.query_api()

FIELDS = ("voltage", "current", "power", "energy", "frequency", "power_factor")
BOOL_FIELDS = ("relay", "power_alarm")


def write_telemetry(device_id: str, site_id: str | None, payload: dict) -> None:
    point = Point("telemetry").tag("device_id", device_id)
    if site_id:
        point = point.tag("site_id", site_id)
    for field in FIELDS:
        if field in payload and payload[field] is not None:
            point = point.field(field, float(payload[field]))
    for field in BOOL_FIELDS:
        if field in payload and payload[field] is not None:
            point = point.field(field, bool(payload[field]))

    ts = payload.get("ts")
    if ts is not None:
        point = point.time(datetime.fromtimestamp(ts, tz=timezone.utc), WritePrecision.S)

    _write_api.write(bucket=settings.influx_bucket, record=point)


def query_history(device_id: str, range_start: str = "-24h", every: str = "1m") -> list[dict]:
    fields_filter = " or ".join(f'r._field == "{f}"' for f in FIELDS)
    flux = f'''
    from(bucket: "{settings.influx_bucket}")
      |> range(start: {range_start})
      |> filter(fn: (r) => r._measurement == "telemetry" and r.device_id == "{device_id}" and ({fields_filter}))
      |> aggregateWindow(every: {every}, fn: mean, createEmpty: false)
      |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")
      |> sort(columns: ["_time"])
    '''
    tables = _query_api.query(flux)
    rows: list[dict] = []
    for table in tables:
        for record in table.records:
            row = {"time": record.get_time().isoformat()}
            for field in FIELDS:
                row[field] = record.values.get(field)
            rows.append(row)
    return rows


def query_monthly_energy(device_id: str) -> float:
    """Điện năng tiêu thụ từ đầu tháng dương lịch hiện tại đến giờ (kWh).

    Cộng dồn các mức tăng dương giữa 2 lần đo liên tiếp thay vì lấy hiệu số
    đầu-cuối, để không bị âm khi bộ đếm điện năng trên thiết bị bị reset
    (mất điện, khởi động lại).
    """
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    flux = f'''
    from(bucket: "{settings.influx_bucket}")
      |> range(start: {month_start.strftime("%Y-%m-%dT%H:%M:%SZ")})
      |> filter(fn: (r) => r._measurement == "telemetry" and r.device_id == "{device_id}" and r._field == "energy")
      |> sort(columns: ["_time"])
    '''
    tables = _query_api.query(flux)
    values = [record.get_value() for table in tables for record in table.records]
    total = 0.0
    for prev, curr in zip(values, values[1:]):
        diff = curr - prev
        if diff > 0:
            total += diff
    return total


def query_latest(device_id: str) -> dict | None:
    flux = f'''
    from(bucket: "{settings.influx_bucket}")
      |> range(start: -1h)
      |> filter(fn: (r) => r._measurement == "telemetry" and r.device_id == "{device_id}")
      |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")
      |> sort(columns: ["_time"], desc: true)
      |> limit(n: 1)
    '''
    tables = _query_api.query(flux)
    for table in tables:
        for record in table.records:
            row = {"time": record.get_time().isoformat()}
            for field in FIELDS + BOOL_FIELDS:
                row[field] = record.values.get(field)
            return row
    return None
