import os  # noqa: F401  # Kept as compatibility export for tests monkeypatching server.os.startfile.

from flask import Flask

from services.app_context import logger


def _add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET,POST,OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type,Authorization'
    return response


def create_app() -> Flask:
    app = Flask(__name__)
    app.after_request(_add_cors_headers)

    from blueprints.assets import assets_bp
    from blueprints.duplicates import duplicates_bp
    from blueprints.settings import settings_bp
    from blueprints.tags import tags_bp
    from blueprints.ui import ui_bp
    from blueprints.updates import updates_bp

    app.register_blueprint(ui_bp)
    app.register_blueprint(tags_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(assets_bp)
    app.register_blueprint(duplicates_bp)
    app.register_blueprint(updates_bp)
    return app


app = create_app()


if __name__ == '__main__':
    logger.info('Bubba Asset Viewer server started on http://localhost:5001')
    app.run(debug=True, port=5001)
    
