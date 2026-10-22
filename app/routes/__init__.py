"""
Routes package for LeetCode Streak Guardian.
Organizes application routes into modular sub-modules:
- auth: registration, login, logout, landing page
- dashboard: authenticated dashboard & manual activity check
- settings: user configuration, notifications, test alerts
- api: cron webhook, desktop companion status, telegram webhook/status, health
"""

from flask import Blueprint

main = Blueprint("main", __name__)

# Import route submodules to register routes onto the main blueprint
from app.routes import auth, dashboard, settings, api  # noqa: E402, F401


def register_blueprints(app):
    """Register application blueprints."""
    app.register_blueprint(main)
