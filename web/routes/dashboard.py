"""페이지 라우트."""

from flask import Blueprint, current_app, render_template, send_from_directory

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/")
def index():
    return render_template("index.html")


@dashboard_bp.route("/manifest.json")
def manifest():
    # scope 를 "/" 로 두기 위해 루트에서 제공
    return send_from_directory(current_app.static_folder, "manifest.json",
                               mimetype="application/manifest+json")
