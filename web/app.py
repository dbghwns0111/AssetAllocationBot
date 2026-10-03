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
    # git pull 후 서버 재시작 전이라도 새 템플릿을 쓰도록 (템플릿 캐시가 옛 HTML 을 붙잡아
    # 새 app.js 와 어긋나면 화면이 깨진다)
    app.config["TEMPLATES_AUTO_RELOAD"] = True
    app.jinja_env.auto_reload = True

    static_dir = os.path.join(_HERE, "static")

    @app.context_processor
    def _asset_version():
        # CSS/JS 수정 시각을 주소에 붙여 브라우저가 옛 파일을 캐시로 쓰지 않게 한다
        try:
            v = int(max(os.path.getmtime(os.path.join(static_dir, f))
                        for f in ("js/app.js", "js/backtest.js", "css/app.css")))
        except OSError:
            v = 0
        return {"asset_v": v}

    from web.routes.api import api_bp
    from web.routes.dashboard import dashboard_bp
    app.register_blueprint(api_bp)
    app.register_blueprint(dashboard_bp)

    from web.auth import init_auth
    init_auth(app)
    return app
