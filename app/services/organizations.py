from __future__ import annotations

import uuid

from sqlalchemy import select

from app.models import Apartment, Building, DomainState, DomainType, OrganizationDomain
from app.services import ServiceValidationError, SessionLike
from app.services.tenancy import require_building, require_organization


def create_apartment(
    session: SessionLike,
    *,
    organization_id: uuid.UUID,
    building_id: uuid.UUID,
    number: str,
    floor: str | None = None,
    block: str | None = None,
    unit_code: str | None = None,
) -> Apartment:
    require_organization(session, organization_id)
    require_building(session, organization_id, building_id)
    apartment = Apartment(
        organization_id=organization_id,
        building_id=building_id,
        number=number,
        floor=floor,
        block=block,
        unit_code=unit_code,
    )
    session.add(apartment)
    return apartment


def create_organization_domain(
    session: SessionLike,
    *,
    organization_id: uuid.UUID,
    hostname: str,
    domain_type: DomainType,
    state: DomainState = DomainState.PENDING,
    is_primary: bool = False,
    is_active: bool = False,
) -> OrganizationDomain:
    require_organization(session, organization_id)
    if is_primary:
        existing_primary = session.scalar(
            select(OrganizationDomain.id).where(
                OrganizationDomain.organization_id == organization_id,
                OrganizationDomain.is_primary.is_(True),
            )
        )
        if existing_primary is not None:
            raise ServiceValidationError(
                "Organization already has a primary domain."
            )
    domain = OrganizationDomain(
        organization_id=organization_id,
        hostname=hostname,
        domain_type=domain_type,
        state=state,
        is_primary=is_primary,
        is_active=is_active,
    )
    session.add(domain)
    return domain


def create_building(
    session: SessionLike,
    *,
    organization_id: uuid.UUID,
    name: str,
    code: str | None = None,
) -> Building:
    require_organization(session, organization_id)
    building = Building(organization_id=organization_id, name=name, code=code)
    session.add(building)
    return building
