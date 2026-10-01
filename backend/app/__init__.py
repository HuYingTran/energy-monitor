from flask import Flask

from app import mqtt_service
from app.config import settings
from app.database import Base, engine


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["SECRET_KEY"] = settings.secret_key

    Base.metadata.create_all(bind=engine)
    mqtt_service.start()

    from app.routes import bp

    app.register_blueprint(bp)

    return app
