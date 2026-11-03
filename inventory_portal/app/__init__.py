from flask import Flask, jsonify
from werkzeug.exceptions import HTTPException

from .config import Config
from .models import db
from .routes import api


def create_app(config_object=Config):
    app = Flask(__name__)
    app.config.from_object(config_object)
    db.init_app(app)
    app.register_blueprint(api)

    with app.app_context():
        db.create_all()

    @app.errorhandler(HTTPException)
    def http_error(exc):
        return jsonify({"error": exc.description}), exc.code

    return app
