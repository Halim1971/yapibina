import pytest
from flask import Flask, g
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import (
    DomainState,
    DomainType,
    Organization,
    OrganizationDomain,
    OrganizationStatus,
)
from app.services import ServiceValidationError
from app.services.organizations import create_organization_domain
from app.tenant.resolver import resolve_request_tenant


def make_organization(
    *,
    name: str = "Örnek Yönetim",
    slug: str = "ornek-yonetim",
    status: OrganizationStatus = OrganizationStatus.ACTIVE,
) -> Organization:
    organization = Organization(name=name, slug=slug, status=status)
    db.session.add(organization)
    db.session.flush()
    return organization


def test_organization_slug_is_normalized_and_unique(app: Flask) -> None:
    del app
    first = make_organization(slug="  Örnek Yönetim ")
    assert first.slug == "ornek-yonetim"
    db.session.commit()

    db.session.add(Organization(name="Other", slug="ÖRNEK YÖNETİM"))
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_domain_hostname_is_normalized_and_globally_unique(app: Flask) -> None:
    del app
    first_org = make_organization(slug="first")
    second_org = make_organization(slug="second")
    first = OrganizationDomain(
        organization_id=first_org.id,
        hostname=" PANEL.Example.COM. ",
        domain_type=DomainType.CUSTOM_DOMAIN,
    )
    db.session.add(first)
    db.session.commit()
    assert first.hostname == "panel.example.com"

    db.session.add(
        OrganizationDomain(
            organization_id=second_org.id,
            hostname="panel.example.com",
            domain_type=DomainType.CUSTOM_DOMAIN,
        )
    )
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_second_primary_domain_is_rejected_by_service(app: Flask) -> None:
    del app
    organization = make_organization()
    create_organization_domain(
        db.session,
        organization_id=organization.id,
        hostname="first.yapibina.com",
        domain_type=DomainType.PLATFORM_SUBDOMAIN,
        is_primary=True,
    )
    db.session.flush()

    with pytest.raises(ServiceValidationError, match="primary"):
        create_organization_domain(
            db.session,
            organization_id=organization.id,
            hostname="second.yapibina.com",
            domain_type=DomainType.PLATFORM_SUBDOMAIN,
            is_primary=True,
        )


def _add_domain(
    organization: Organization,
    *,
    hostname: str,
    state: DomainState = DomainState.ACTIVE,
    is_active: bool = True,
) -> None:
    db.session.add(
        OrganizationDomain(
            organization_id=organization.id,
            hostname=hostname,
            domain_type=DomainType.CUSTOM_DOMAIN,
            state=state,
            is_active=is_active,
            is_primary=True,
        )
    )
    db.session.commit()


def test_only_active_domain_and_organization_resolve(app: Flask) -> None:
    organization = make_organization()
    _add_domain(organization, hostname="tenant.example.com")

    with app.test_request_context("/", headers={"Host": "tenant.example.com"}):
        resolve_request_tenant()

        assert g.tenant.organization_id == str(organization.id)
        assert g.tenant.organization_slug == organization.slug
        assert g.tenant.hostname == "tenant.example.com"


@pytest.mark.parametrize(
    ("organization_status", "domain_state", "domain_active"),
    [
        (OrganizationStatus.SUSPENDED, DomainState.ACTIVE, True),
        (OrganizationStatus.ACTIVE, DomainState.SUSPENDED, True),
        (OrganizationStatus.ACTIVE, DomainState.ACTIVE, False),
    ],
)
def test_inactive_tenant_conditions_do_not_resolve(
    app: Flask,
    organization_status: OrganizationStatus,
    domain_state: DomainState,
    domain_active: bool,
) -> None:
    organization = make_organization(status=organization_status)
    _add_domain(
        organization,
        hostname="inactive.example.com",
        state=domain_state,
        is_active=domain_active,
    )

    response = app.test_client().get(
        "/missing",
        headers={"Host": "inactive.example.com", "Accept": "application/json"},
    )

    assert response.status_code == 421


def test_platform_hostname_is_not_a_tenant(app: Flask) -> None:
    with app.test_request_context(
        "/platform/missing",
        headers={"Host": "platform.yapibina.com"},
    ):
        resolve_request_tenant()

        assert g.tenant is None
        assert g.is_platform_request is True
