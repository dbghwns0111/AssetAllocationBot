"""Flask 앱 팩토리."""

from __future__ import annotations

import os

from flask import Flask

_HERE = os.path.dirname(os.path.abspath(__file__))


def create_app(cfg: dict, notifier=None, scheduler=None) -> Flask:
    app = Flask(
        __name__,
        template_folder=os.path.join(_HERE, "templates"),
        static_folder=os.path.join(_HERE, "static"),
    )
    app.config["CFG"] = cfg
    app.config["NOTIFIER"] = notifier
    app.config["SCHEDULER"] = scheduler
    app.config["JSON_AS_ASCII"] = False
    app.json.ensure_ascii = False

    from web.routes.api import api_bp
    from web.routes.dashboard import dashboard_bp
    app.register_blueprint(api_bp)
    app.register_blueprint(dashboard_bp)

    from web.auth import init_auth
    init_auth(app)
    return app
