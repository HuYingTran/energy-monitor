import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class Site(Base):
    __tablename__ = "sites"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    devices: Mapped[list["Device"]] = relationship(back_populates="site")


class Device(Base):
    __tablename__ = "devices"

    # device_id đúng bằng {device_id} dùng trong topic MQTT (VD MAC address)
    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    site_id: Mapped[str | None] = mapped_column(ForeignKey("sites.id"), nullable=True)
    online: Mapped[bool] = mapped_column(Boolean, default=False)
    relay_state: Mapped[bool] = mapped_column(Boolean, default=True)
    firmware_version: Mapped[str | None] = mapped_column(String, nullable=True)
    last_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    site: Mapped[Site | None] = relationship(back_populates="devices")
    alert_rules: Mapped[list["AlertRule"]] = relationship(back_populates="device", cascade="all, delete-orphan")
    relay_events: Mapped[list["RelayEvent"]] = relationship(back_populates="device", cascade="all, delete-orphan")


class AlertRule(Base):
    __tablename__ = "alert_rules"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id"), nullable=False)
    rule_type: Mapped[str] = mapped_column(String, nullable=False)  # power_max | offline_timeout
    threshold: Mapped[float] = mapped_column(Float, nullable=False)
    auto_cutoff: Mapped[bool] = mapped_column(Boolean, default=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    device: Mapped[Device] = relationship(back_populates="alert_rules")


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id"), nullable=False)
    rule_id: Mapped[str | None] = mapped_column(ForeignKey("alert_rules.id"), nullable=True)
    message: Mapped[str] = mapped_column(String, nullable=False)
    triggered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RelayEvent(Base):
    __tablename__ = "relay_events"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id"), nullable=False)
    value: Mapped[bool] = mapped_column(Boolean, nullable=False)
    source: Mapped[str] = mapped_column(String, nullable=False)  # user | rule | auto
    request_id: Mapped[str | None] = mapped_column(String, nullable=True)
    acked: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    device: Mapped[Device] = relationship(back_populates="relay_events")
