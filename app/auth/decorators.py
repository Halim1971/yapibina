from __future__ import annotations

import uuid
from collections.abc import Callable
from functools import wraps
from typing import Any, ParamSpec, TypeVar, cast

from flask import abort, g, redirect, session, url_for
from flask_login import current_user, logout_user

from app.auth.policies import (
    can_access_apartment,
    can_access_building,
    can_access_platform,
    effective_organization_membership,
    is_active_user,
    scoped_apartment,
    scoped_building,
)
from app.extensions import db, login_manager
from app.models import OrganizationMembershipRole, User

P = ParamSpec("P")
R = TypeVar("R")


def _current_active_user() -> User | None:
    if not current_user.is_authenticated:
        return None
    user = db.session.get(User, current_user.id)
    if user is None or not is_active_user(user):
        logout_user()
        session.clear()
        return None
    return user


def _login_redirect() -> Any:
    if current_user.is_authenticated:
        return redirect(url_for("auth.login"))
    return login_manager.unauthorized()


def _tenant_organization_id() -> uuid.UUID | None:
    if g.tenant is None:
        return None
    try:
        return uuid.UUID(g.tenant.organization_id)
    except (ValueError, TypeError, AttributeError):
        return None


def platform_admin_required(view: Callable[P, R]) -> Callable[P, R]:
    @wraps(view)
    def wrapped(*args: P.args, **kwargs: P.kwargs) -> R:
        user = _current_active_user()
        if user is None:
            return cast(R, _login_redirect())
        if not can_access_platform(
            user,
            tenant=g.tenant,
            is_platform_request=bool(g.is_platform_request),
        ):
            abort(403)
        return view(*args, **kwargs)

    return wrapped


def organization_member_required(view: Callable[P, R]) -> Callable[P, R]:
    @wraps(view)
    def wrapped(*args: P.args, **kwargs: P.kwargs) -> R:
        user = _current_active_user()
        if user is None:
            return cast(R, _login_redirect())
        organization_id = _tenant_organization_id()
        if organization_id is None:
            abort(403)
        membership = effective_organization_membership(
            db.session,
            user_id=user.id,
            organization_id=organization_id,
        )
        if membership is None:
            abort(403)
        g.organization_membership = membership
        return view(*args, **kwargs)

    return wrapped


def organization_admin_required(view: Callable[P, R]) -> Callable[P, R]:
    @organization_member_required
    @wraps(view)
    def wrapped(*args: P.args, **kwargs: P.kwargs) -> R:
        if (
            g.organization_membership.role
            is not OrganizationMembershipRole.ORGANIZATION_ADMIN
        ):
            abort(403)
        return view(*args, **kwargs)

    return wrapped


def building_access_required(view: Callable[P, R]) -> Callable[P, R]:
    @wraps(view)
    def wrapped(*args: P.args, **kwargs: P.kwargs) -> R:
        user = _current_active_user()
        if user is None:
            return cast(R, _login_redirect())
        organization_id = _tenant_organization_id()
        building_id = _parse_resource_id(kwargs.get("building_id"))
        if organization_id is None or building_id is None:
            abort(404)
        building = scoped_building(
            db.session,
            organization_id=organization_id,
            building_id=building_id,
        )
        if building is None:
            abort(404)
        if not can_access_building(
            db.session,
            user=user,
            organization_id=organization_id,
            building=building,
        ):
            abort(403)
        g.building = building
        return view(*args, **kwargs)

    return wrapped


def resident_apartment_access_required(view: Callable[P, R]) -> Callable[P, R]:
    @wraps(view)
    def wrapped(*args: P.args, **kwargs: P.kwargs) -> R:
        user = _current_active_user()
        if user is None:
            return cast(R, _login_redirect())
        organization_id = _tenant_organization_id()
        apartment_id = _parse_resource_id(kwargs.get("apartment_id"))
        if organization_id is None or apartment_id is None:
            abort(404)
        apartment = scoped_apartment(
            db.session,
            organization_id=organization_id,
            apartment_id=apartment_id,
        )
        if apartment is None:
            abort(404)
        if not can_access_apartment(
            db.session,
            user=user,
            organization_id=organization_id,
            apartment=apartment,
        ):
            abort(403)
        g.apartment = apartment
        return view(*args, **kwargs)

    return wrapped


def resident_required(view: Callable[P, R]) -> Callable[P, R]:
    @wraps(view)
    def wrapped(*args: P.args, **kwargs: P.kwargs) -> R:
        user = _current_active_user()
        if user is None:
            return cast(R, _login_redirect())
        organization_id = _tenant_organization_id()
        if organization_id is None or user.is_platform_super_admin:
            abort(403)
        membership = effective_organization_membership(
            db.session,
            user_id=user.id,
            organization_id=organization_id,
        )
        if (
            membership is None
            or membership.role is not OrganizationMembershipRole.ORGANIZATION_MEMBER
        ):
            abort(403)
        g.organization_membership = membership
        return view(*args, **kwargs)

    return wrapped


def _parse_resource_id(value: object) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        return None
