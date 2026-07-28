from __future__ import annotations

import uuid

from app.models import Apartment, Building, Organization, User
from app.services import EntityNotFoundError, SessionLike, TenantBoundaryError


def require_organization(
    session: SessionLike,
    organization_id: uuid.UUID,
) -> Organization:
    organization = session.get(Organization, organization_id)
    if organization is None:
        raise EntityNotFoundError("Organization was not found.")
    return organization


def require_user(session: SessionLike, user_id: uuid.UUID) -> User:
    user = session.get(User, user_id)
    if user is None:
        raise EntityNotFoundError("User was not found.")
    return user


def require_building(
    session: SessionLike,
    organization_id: uuid.UUID,
    building_id: uuid.UUID,
) -> Building:
    building = session.get(Building, building_id)
    if building is None:
        raise EntityNotFoundError("Building was not found.")
    if building.organization_id != organization_id:
        raise TenantBoundaryError("Building does not belong to the organization.")
    return building


def require_apartment(
    session: SessionLike,
    organization_id: uuid.UUID,
    apartment_id: uuid.UUID,
) -> Apartment:
    apartment = session.get(Apartment, apartment_id)
    if apartment is None:
        raise EntityNotFoundError("Apartment was not found.")
    if apartment.organization_id != organization_id:
        raise TenantBoundaryError("Apartment does not belong to the organization.")
    return apartment
