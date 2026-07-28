from __future__ import annotations

import logging

from flask import (
    current_app,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_login import current_user, login_user, logout_user
from werkzeug.wrappers import Response

from app.auth.session import is_safe_next_url, renew_session
from app.blueprints.auth import auth_blueprint
from app.blueprints.auth.forms import LoginForm
from app.blueprints.auth.services import authenticate_user
from app.extensions import db, limiter
from app.models.base import utc_now

logger = logging.getLogger(__name__)

INVALID_CREDENTIALS_MESSAGE = "E-posta adresi veya parola hatalı."


def _configured_login_limits() -> str:
    return str(current_app.config["LOGIN_RATE_LIMITS"])


@auth_blueprint.route("/login", methods=["GET", "POST"])
@limiter.limit(_configured_login_limits, methods=["POST"])
def login() -> Response | str:
    if current_user.is_authenticated:
        destination = "/platform/" if current_user.is_platform_super_admin else "/organization/"
        return redirect(destination)

    form = LoginForm()
    if form.validate_on_submit():
        result = authenticate_user(
            db.session,
            email=form.email.data,
            password=form.password.data,
            tenant=g.tenant,
            is_platform_request=bool(g.is_platform_request),
        )
        if result is None:
            flash(INVALID_CREDENTIALS_MESSAGE, "error")
        else:
            result.user.last_login_at = utc_now()
            db.session.commit()
            renew_session()
            login_user(
                result.user,
                remember=bool(form.remember_me.data),
                fresh=True,
            )
            logger.info(
                "Authentication succeeded",
                extra={
                    "user_id": str(result.user.id),
                    "organization_id": (
                        g.tenant.organization_id if g.tenant is not None else None
                    ),
                },
            )
            next_url = request.args.get("next")
            if next_url is not None and is_safe_next_url(next_url):
                return redirect(next_url)
            return redirect(result.destination)
    elif request.method == "POST":
        flash(INVALID_CREDENTIALS_MESSAGE, "error")

    return render_template("auth/login.html", form=form)


@auth_blueprint.post("/logout")
def logout() -> Response:
    logout_user()
    session.clear()
    return redirect(url_for("auth.login"))
