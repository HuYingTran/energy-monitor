from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    sqlite_path: str = "energy_monitor.db"

    influx_url: str = "http://localhost:8086"
    influx_org: str = "energy-monitor"
    influx_bucket: str = "telemetry"
    influx_token: str = "dev-super-secret-admin-token"

    mqtt_host: str = "localhost"
    mqtt_port: int = 1883

    secret_key: str = "dev-secret-key-change-me"

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.sqlite_path}"

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
