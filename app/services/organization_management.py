from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models import Apartment, Building
from app.services import DuplicateEntityError, SessionLike
from app.services.tenancy import require_apartment, require_building, require_organization


def create_building(
    session: SessionLike,
    *,
    organization_id: uuid.UUID,
    name: str,
    code: str,
    address_line: str | None,
    district: str | None,
    city: str | None,
    postal_code: str | None,
    is_active: bool,
) -> Building:
    require_organization(session, organization_id)
    normalized_code = code.strip()
    if session.scalar(
        select(Building.id).where(
            Building.organization_id == organization_id,
            Building.code == normalized_code,
        )
    ):
        raise DuplicateEntityError("Bu bina kodu organization içinde kullanılıyor.")
    building = Building(
        organization_id=organization_id,
        name=name.strip(),
        code=normalized_code,
        address_line=address_line or None,
        district=district or None,
        city=city or None,
        postal_code=postal_code or None,
        is_active=is_active,
    )
    session.add(building)
    try:
        session.flush()
    except IntegrityError as error:
        raise DuplicateEntityError("Bu bina kodu organization içinde kullanılıyor.") from error
    return building


def update_building(
    session: SessionLike, *, organization_id: uuid.UUID, building_id: uuid.UUID, **values: object
) -> Building:
    building = require_building(session, organization_id, building_id)
    code = str(values["code"]).strip()
    duplicate = session.scalar(
        select(Building.id).where(
            Building.organization_id == organization_id,
            Building.code == code,
            Building.id != building_id,
        )
    )
    if duplicate:
        raise DuplicateEntityError("Bu bina kodu organization içinde kullanılıyor.")
    building.name = str(values["name"]).strip()
    building.code = code
    building.address_line = str(values["address_line"]) if values["address_line"] else None
    building.district = str(values["district"]) if values["district"] else None
    building.city = str(values["city"]) if values["city"] else None
    building.postal_code = str(values["postal_code"]) if values["postal_code"] else None
    building.is_active = bool(values["is_active"])
    session.flush()
    return building


def create_apartment(
    session: SessionLike,
    *,
    organization_id: uuid.UUID,
    building_id: uuid.UUID,
    number: str,
    floor: str | None,
    block: str | None,
    unit_code: str,
    is_active: bool,
) -> Apartment:
    require_building(session, organization_id, building_id)
    normalized_code = unit_code.strip()
    if session.scalar(
        select(Apartment.id).where(
            Apartment.building_id == building_id, Apartment.unit_code == normalized_code
        )
    ):
        raise DuplicateEntityError("Bu daire kodu bina içinde kullanılıyor.")
    apartment = Apartment(
        organization_id=organization_id,
        building_id=building_id,
        number=number.strip(),
        floor=floor or None,
        block=block or None,
        unit_code=normalized_code,
        is_active=is_active,
    )
    session.add(apartment)
    try:
        session.flush()
    except IntegrityError as error:
        raise DuplicateEntityError("Bu daire kodu bina içinde kullanılıyor.") from error
    return apartment


def update_apartment(
    session: SessionLike,
    *,
    organization_id: uuid.UUID,
    apartment_id: uuid.UUID,
    number: str,
    floor: str | None,
    block: str | None,
    unit_code: str,
    is_active: bool,
) -> Apartment:
    apartment = require_apartment(session, organization_id, apartment_id)
    normalized_code = unit_code.strip()
    duplicate = session.scalar(
        select(Apartment.id).where(
            Apartment.building_id == apartment.building_id,
            Apartment.unit_code == normalized_code,
            Apartment.id != apartment_id,
        )
    )
    if duplicate:
        raise DuplicateEntityError("Bu daire kodu bina içinde kullanılıyor.")
    apartment.number = number.strip()
    apartment.floor = floor or None
    apartment.block = block or None
    apartment.unit_code = normalized_code
    apartment.is_active = is_active
    session.flush()
    return apartment
