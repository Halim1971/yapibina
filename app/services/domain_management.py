from __future__ import annotations

import secrets
import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models import DomainState, DomainType, OrganizationDomain
from app.models.base import normalize_hostname_value
from app.services import (
    DuplicateEntityError,
    InvalidStateTransitionError,
    SessionLike,
)
from app.services.tenancy import require_organization

TRANSITIONS: dict[DomainState, frozenset[DomainState]] = {
    DomainState.PENDING: frozenset({DomainState.AWAITING_DNS}),
    DomainState.AWAITING_DNS: frozenset({DomainState.DNS_VERIFIED}),
    DomainState.DNS_VERIFIED: frozenset({DomainState.SSL_PENDING}),
    DomainState.SSL_PENDING: frozenset({DomainState.ACTIVE}),
    DomainState.ACTIVE: frozenset({DomainState.SUSPENDED}),
    DomainState.FAILED: frozenset({DomainState.AWAITING_DNS}),
    DomainState.SUSPENDED: frozenset({DomainState.AWAITING_DNS, DomainState.ACTIVE}),
}


def _scoped_domain(
    session: SessionLike,
    organization_id: uuid.UUID,
    domain_id: uuid.UUID,
) -> OrganizationDomain:
    domain = session.scalar(
        select(OrganizationDomain).where(
            OrganizationDomain.id == domain_id,
            OrganizationDomain.organization_id == organization_id,
        )
    )
    if domain is None:
        from app.services import EntityNotFoundError

        raise EntityNotFoundError("Domain bulunamadı.")
    return domain


def create_domain(
    session: SessionLike,
    *,
    organization_id: uuid.UUID,
    hostname: str,
    domain_type: DomainType,
    is_primary: bool,
) -> OrganizationDomain:
    require_organization(session, organization_id)
    normalized = normalize_hostname_value(hostname)
    if session.scalar(
        select(OrganizationDomain.id).where(OrganizationDomain.hostname == normalized)
    ):
        raise DuplicateEntityError("Bu hostname zaten kullanılıyor.")
    if is_primary and session.scalar(
        select(OrganizationDomain.id).where(
            OrganizationDomain.organization_id == organization_id,
            OrganizationDomain.is_primary.is_(True),
        )
    ):
        raise DuplicateEntityError("Organization zaten bir primary domaine sahip.")
    domain = OrganizationDomain(
        organization_id=organization_id,
        hostname=normalized,
        domain_type=domain_type,
        state=DomainState.AWAITING_DNS,
        verification_token=secrets.token_urlsafe(32),
        is_primary=is_primary,
        is_active=False,
    )
    session.add(domain)
    try:
        session.flush()
    except IntegrityError as error:
        raise DuplicateEntityError("Domain kaydı benzersiz olmalıdır.") from error
    return domain


def make_primary(
    session: SessionLike,
    *,
    organization_id: uuid.UUID,
    domain_id: uuid.UUID,
) -> OrganizationDomain:
    domain = _scoped_domain(session, organization_id, domain_id)
    other = session.scalar(
        select(OrganizationDomain).where(
            OrganizationDomain.organization_id == organization_id,
            OrganizationDomain.is_primary.is_(True),
            OrganizationDomain.id != domain_id,
        )
    )
    if other is not None:
        other.is_primary = False
    domain.is_primary = True
    session.flush()
    return domain


def transition_domain(
    session: SessionLike,
    *,
    organization_id: uuid.UUID,
    domain_id: uuid.UUID,
    target: DomainState,
) -> OrganizationDomain:
    domain = _scoped_domain(session, organization_id, domain_id)
    if target not in TRANSITIONS.get(domain.state, frozenset()):
        raise InvalidStateTransitionError(
            f"{domain.state.value} durumundan {target.value} durumuna geçilemez."
        )
    domain.state = target
    domain.is_active = target is DomainState.ACTIVE
    session.flush()
    return domain
