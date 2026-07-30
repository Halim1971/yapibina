from __future__ import annotations

import re
from datetime import timedelta

import pytest
from flask import Flask
from flask.testing import FlaskClient
from sqlalchemy import event, select
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import (
    Announcement,
    AnnouncementAudienceScope,
    AnnouncementRead,
    AnnouncementStatus,
    Apartment,
    ApartmentMembership,
    ApartmentMembershipRole,
    Building,
    BuildingMembership,
    BuildingMembershipRole,
    DomainState,
    DomainType,
    Organization,
    OrganizationDomain,
    OrganizationMembership,
    OrganizationMembershipRole,
    OrganizationStatus,
    User,
    UserStatus,
)
from app.models.base import utc_now
from app.services import (
    EntityNotFoundError,
    InvalidStateTransitionError,
    ServiceValidationError,
)
from app.services.organization_announcements import (
    archive_announcement,
    create_announcement,
    get_organization_announcement,
    list_organization_announcements,
    publish_announcement,
    update_draft_announcement,
)
from app.services.resident_announcements import (
    get_resident_announcement,
    list_resident_announcements,
)
from app.services.resident_notifications import (
    get_announcement_read_state,
    get_unread_announcement_count,
    list_resident_notifications,
    mark_announcement_read,
)

HOST = "announcement.example.com"
PASSWORD = "SecurePass123"


@pytest.fixture(autouse=True)
def _application_context(app: Flask) -> None:
    del app


def _user(email: str, first_name: str = "Duyuru", last_name: str = "Kullanıcı") -> User:
    user = User(
        email=email,
        password_hash="",
        first_name=first_name,
        last_name=last_name,
    )
    user.set_password(PASSWORD)
    db.session.add(user)
    db.session.flush()
    return user


def _organization(slug: str, hostname: str) -> Organization:
    organization = Organization(
        name=slug.title(),
        slug=slug,
        status=OrganizationStatus.ACTIVE,
    )
    db.session.add(organization)
    db.session.flush()
    db.session.add(
        OrganizationDomain(
            organization_id=organization.id,
            hostname=hostname,
            domain_type=DomainType.CUSTOM_DOMAIN,
            state=DomainState.ACTIVE,
            is_active=True,
            is_primary=True,
        )
    )
    db.session.flush()
    return organization


def _membership(
    organization: Organization,
    user: User,
    role: OrganizationMembershipRole,
) -> None:
    db.session.add(
        OrganizationMembership(
            organization_id=organization.id,
            user_id=user.id,
            role=role,
            starts_at=utc_now() - timedelta(days=1),
        )
    )
    db.session.flush()


def _building(organization: Organization, code: str, *, active: bool = True) -> Building:
    building = Building(
        organization_id=organization.id,
        name=f"{code} Apartmanı",
        code=code,
        is_active=active,
    )
    db.session.add(building)
    db.session.flush()
    return building


def _resident_in_building(
    organization: Organization,
    building: Building,
    email: str,
    *,
    active_membership: bool = True,
) -> User:
    resident = _user(email)
    _membership(
        organization, resident, OrganizationMembershipRole.ORGANIZATION_MEMBER
    )
    unit_key = email.split("@", 1)[0]
    apartment = Apartment(
        organization_id=organization.id,
        building_id=building.id,
        number=unit_key[:30],
        unit_code=f"{building.code}-{unit_key}"[:60],
        is_active=True,
    )
    db.session.add(apartment)
    db.session.flush()
    db.session.add(
        ApartmentMembership(
            organization_id=organization.id,
            apartment_id=apartment.id,
            user_id=resident.id,
            role=ApartmentMembershipRole.RESIDENT,
            is_active=active_membership,
            starts_at=utc_now() - timedelta(days=1),
        )
    )
    db.session.flush()
    return resident


def _scope() -> tuple[Organization, User, Building, Building]:
    organization = _organization("announcement", HOST)
    admin = _user("announcement-admin@example.com", "Yönetim", "Sorumlusu")
    _membership(
        organization, admin, OrganizationMembershipRole.ORGANIZATION_ADMIN
    )
    first = _building(organization, "A")
    second = _building(organization, "B")
    db.session.commit()
    return organization, admin, first, second


def _session_login(client: FlaskClient, user: User, host: str = HOST) -> None:
    with client.session_transaction(headers={"Host": host}) as session:
        session["_user_id"] = str(user.id)
        session["_fresh"] = True


def _login(client: FlaskClient, user: User, host: str = HOST) -> None:
    response = client.post(
        "/auth/login",
        data={"email": user.email, "password": PASSWORD},
        headers={"Host": host},
    )
    assert response.status_code == 302


def test_announcement_model_targets_and_lifecycle() -> None:
    organization, admin, first, second = _scope()
    draft = create_announcement(
        db.session,
        organization_id=organization.id,
        created_by_user_id=admin.id,
        title="  Su Kesintisi  ",
        body="Çalışma nedeniyle kısa süreli kesinti olacaktır.",
        audience_scope=AnnouncementAudienceScope.BUILDINGS,
        building_ids=(first.id, second.id),
    )
    assert draft.title == "Su Kesintisi"
    assert draft.status is AnnouncementStatus.DRAFT
    assert len(draft.building_targets) == 2

    update_draft_announcement(
        db.session,
        organization_id=organization.id,
        announcement_id=draft.id,
        title="Su Kesintisi Güncellemesi",
        body="Çalışma tamamlanmıştır.",
        audience_scope=AnnouncementAudienceScope.ORGANIZATION,
    )
    assert draft.building_targets == []
    assert publish_announcement(
        db.session,
        organization_id=organization.id,
        announcement_id=draft.id,
    ) is draft
    assert publish_announcement(
        db.session,
        organization_id=organization.id,
        announcement_id=draft.id,
    ) is draft
    with pytest.raises(InvalidStateTransitionError):
        update_draft_announcement(
            db.session,
            organization_id=organization.id,
            announcement_id=draft.id,
            title="Sessiz değişiklik",
            body="Reddedilmeli",
            audience_scope=AnnouncementAudienceScope.ORGANIZATION,
        )
    assert archive_announcement(
        db.session,
        organization_id=organization.id,
        announcement_id=draft.id,
    ) is draft
    assert archive_announcement(
        db.session,
        organization_id=organization.id,
        announcement_id=draft.id,
    ) is draft
    with pytest.raises(InvalidStateTransitionError):
        publish_announcement(
            db.session,
            organization_id=organization.id,
            announcement_id=draft.id,
        )

    scheduled = create_announcement(
        db.session,
        organization_id=organization.id,
        created_by_user_id=admin.id,
        title="Planlı Duyuru",
        body="Yarın yayınlanacak.",
        audience_scope=AnnouncementAudienceScope.BUILDINGS,
        building_ids=(first.id,),
        publish_at=utc_now() + timedelta(days=1),
    )
    updated_publish_at = utc_now() + timedelta(days=2)
    update_draft_announcement(
        db.session,
        organization_id=organization.id,
        announcement_id=scheduled.id,
        title="Planlı Duyuru Güncellendi",
        body="İki gün sonra yayınlanacak.",
        audience_scope=AnnouncementAudienceScope.BUILDINGS,
        building_ids=(second.id,),
        publish_at=updated_publish_at,
    )
    assert scheduled.status is AnnouncementStatus.PUBLISHED
    assert scheduled.building_targets[0].building_id == second.id
    with pytest.raises(InvalidStateTransitionError):
        update_draft_announcement(
            db.session,
            organization_id=organization.id,
            announcement_id=scheduled.id,
            title="Taslağa dönüş",
            body="İzin verilmemeli.",
            audience_scope=AnnouncementAudienceScope.ORGANIZATION,
        )


def test_database_rejects_published_announcement_without_publication_time() -> None:
    organization, admin, _, _ = _scope()
    db.session.add(
        Announcement(
            organization_id=organization.id,
            created_by_user_id=admin.id,
            title="Geçersiz published",
            body="published_at eksik.",
            status=AnnouncementStatus.PUBLISHED,
            audience_scope=AnnouncementAudienceScope.ORGANIZATION,
        )
    )
    with pytest.raises(IntegrityError):
        db.session.flush()
    db.session.rollback()


def test_target_and_date_validation_is_tenant_safe() -> None:
    organization, admin, first, _ = _scope()
    inactive = _building(organization, "PASİF", active=False)
    other = _organization("announcement-other", "announcement-other.example.com")
    hidden = _building(other, "GİZLİ")
    future = utc_now() + timedelta(days=2)
    with pytest.raises(ServiceValidationError):
        create_announcement(
            db.session,
            organization_id=organization.id,
            created_by_user_id=admin.id,
            title="Geçersiz hedef",
            body="Başka tenant hedeflenemez.",
            audience_scope=AnnouncementAudienceScope.BUILDINGS,
            building_ids=(hidden.id,),
        )
    with pytest.raises(ServiceValidationError):
        create_announcement(
            db.session,
            organization_id=organization.id,
            created_by_user_id=admin.id,
            title="Pasif hedef",
            body="Pasif bina hedeflenemez.",
            audience_scope=AnnouncementAudienceScope.BUILDINGS,
            building_ids=(inactive.id,),
        )
    with pytest.raises(ServiceValidationError):
        create_announcement(
            db.session,
            organization_id=organization.id,
            created_by_user_id=admin.id,
            title="Boş hedef",
            body="Bina seçilmedi.",
            audience_scope=AnnouncementAudienceScope.BUILDINGS,
        )
    with pytest.raises(ServiceValidationError):
        create_announcement(
            db.session,
            organization_id=organization.id,
            created_by_user_id=admin.id,
            title="Çelişkili hedef",
            body="Organization hedefi bina taşımamalı.",
            audience_scope=AnnouncementAudienceScope.ORGANIZATION,
            building_ids=(first.id,),
        )
    with pytest.raises(ServiceValidationError):
        create_announcement(
            db.session,
            organization_id=organization.id,
            created_by_user_id=admin.id,
            title="Geçersiz süre",
            body="Bitiş yayından önce.",
            audience_scope=AnnouncementAudienceScope.ORGANIZATION,
            publish_at=future,
            expires_at=future - timedelta(hours=1),
        )
    with pytest.raises(ServiceValidationError):
        create_announcement(
            db.session,
            organization_id=organization.id,
            created_by_user_id=admin.id,
            title="Kontrol\x00karakteri",
            body="Reddedilmeli.",
            audience_scope=AnnouncementAudienceScope.ORGANIZATION,
        )


def test_resident_visibility_covers_scope_time_and_memberships() -> None:
    organization, admin, first, second = _scope()
    resident = _resident_in_building(
        organization, first, "visible-resident@example.com"
    )
    other_resident = _resident_in_building(
        organization, second, "other-resident@example.com"
    )
    second_apartment = Apartment(
        organization_id=organization.id,
        building_id=second.id,
        number="A2",
        unit_code="B-A2",
        is_active=True,
    )
    db.session.add(second_apartment)
    db.session.flush()
    db.session.add(
        ApartmentMembership(
            organization_id=organization.id,
            apartment_id=second_apartment.id,
            user_id=resident.id,
            role=ApartmentMembershipRole.RESIDENT,
            starts_at=utc_now() - timedelta(days=1),
        )
    )
    now = utc_now()
    visible = [
        create_announcement(
            db.session,
            organization_id=organization.id,
            created_by_user_id=admin.id,
            title="Genel Duyuru",
            body="Herkes görür.",
            audience_scope=AnnouncementAudienceScope.ORGANIZATION,
            publish_at=now - timedelta(hours=1),
        ),
        create_announcement(
            db.session,
            organization_id=organization.id,
            created_by_user_id=admin.id,
            title="İki Bina Ortak",
            body="İki hedef eşleşse de bir kez görünür.",
            audience_scope=AnnouncementAudienceScope.BUILDINGS,
            building_ids=(first.id, second.id),
            publish_at=now - timedelta(hours=1),
        ),
        create_announcement(
            db.session,
            organization_id=organization.id,
            created_by_user_id=admin.id,
            title="A Binası",
            body="Yalnız A binası görür.",
            audience_scope=AnnouncementAudienceScope.BUILDINGS,
            building_ids=(first.id,),
            publish_at=now - timedelta(hours=1),
        ),
    ]
    create_announcement(
        db.session,
        organization_id=organization.id,
        created_by_user_id=admin.id,
        title="B Binası",
        body="Yalnız B binası görür.",
        audience_scope=AnnouncementAudienceScope.BUILDINGS,
        building_ids=(second.id,),
        publish_at=now - timedelta(hours=1),
    )
    create_announcement(
        db.session,
        organization_id=organization.id,
        created_by_user_id=admin.id,
        title="Gelecek",
        body="Henüz görünmez.",
        audience_scope=AnnouncementAudienceScope.ORGANIZATION,
        publish_at=now + timedelta(days=1),
    )
    create_announcement(
        db.session,
        organization_id=organization.id,
        created_by_user_id=admin.id,
        title="Süresi Doldu",
        body="Artık görünmez.",
        audience_scope=AnnouncementAudienceScope.ORGANIZATION,
        publish_at=now - timedelta(days=2),
        expires_at=now - timedelta(days=1),
    )
    archived = create_announcement(
        db.session,
        organization_id=organization.id,
        created_by_user_id=admin.id,
        title="Arşiv",
        body="Görünmez.",
        audience_scope=AnnouncementAudienceScope.ORGANIZATION,
        publish_at=now - timedelta(days=1),
    )
    archive_announcement(
        db.session,
        organization_id=organization.id,
        announcement_id=archived.id,
    )
    db.session.commit()

    listing = list_resident_announcements(
        db.session,
        organization_id=organization.id,
        user_id=resident.id,
        now=now,
    )
    assert {item.title for item in listing.items} == {
        "Genel Duyuru",
        "A Binası",
        "B Binası",
        "İki Bina Ortak",
    }
    assert sum(item.title == "İki Bina Ortak" for item in listing.items) == 1
    assert {
        item.title
        for item in list_resident_announcements(
            db.session,
            organization_id=organization.id,
            user_id=other_resident.id,
            now=now,
        ).items
    } == {"Genel Duyuru", "B Binası", "İki Bina Ortak"}
    for announcement in visible:
        assert (
            get_resident_announcement(
                db.session,
                organization_id=organization.id,
                user_id=resident.id,
                announcement_id=announcement.id,
                now=now,
            ).id
            == announcement.id
        )
    hidden = db.session.scalar(
        select(Announcement).where(Announcement.title == "A Binası")
    )
    assert hidden is not None
    with pytest.raises(EntityNotFoundError):
        get_resident_announcement(
            db.session,
            organization_id=organization.id,
            user_id=other_resident.id,
            announcement_id=hidden.id,
            now=now,
        )


def test_resident_without_apartment_sees_only_organization_scope() -> None:
    organization, admin, first, _ = _scope()
    resident = _user("no-apartment@example.com")
    _membership(
        organization, resident, OrganizationMembershipRole.ORGANIZATION_MEMBER
    )
    now = utc_now()
    for title, scope, buildings in (
        ("Organization", AnnouncementAudienceScope.ORGANIZATION, ()),
        ("Building", AnnouncementAudienceScope.BUILDINGS, (first.id,)),
    ):
        create_announcement(
            db.session,
            organization_id=organization.id,
            created_by_user_id=admin.id,
            title=title,
            body="Duyuru metni.",
            audience_scope=scope,
            building_ids=buildings,
            publish_at=now - timedelta(minutes=1),
        )
    db.session.commit()
    listing = list_resident_announcements(
        db.session,
        organization_id=organization.id,
        user_id=resident.id,
        now=now,
    )
    assert [item.title for item in listing.items] == ["Organization"]


def test_organization_routes_authorization_idor_and_escaping(
    client: FlaskClient,
) -> None:
    organization, admin, first, _ = _scope()
    resident = _resident_in_building(
        organization, first, "route-resident@example.com"
    )
    manager = _user("announcement-manager@example.com")
    _membership(
        organization, manager, OrganizationMembershipRole.ORGANIZATION_MEMBER
    )
    db.session.add(
        BuildingMembership(
            organization_id=organization.id,
            building_id=first.id,
            user_id=manager.id,
            role=BuildingMembershipRole.BUILDING_MANAGER,
        )
    )
    other = _organization("route-other", "route-other.example.com")
    other_admin = _user("route-other-admin@example.com")
    _membership(other, other_admin, OrganizationMembershipRole.ORGANIZATION_ADMIN)
    hidden = create_announcement(
        db.session,
        organization_id=other.id,
        created_by_user_id=other_admin.id,
        title="Gizli Duyuru",
        body="Başka tenant içeriği.",
        audience_scope=AnnouncementAudienceScope.ORGANIZATION,
    )
    safe = create_announcement(
        db.session,
        organization_id=organization.id,
        created_by_user_id=admin.id,
        title="<script>alert(1)</script>",
        body="<img src=x onerror=alert(1)>",
        audience_scope=AnnouncementAudienceScope.ORGANIZATION,
        publish_at=utc_now(),
    )
    db.session.commit()

    assert (
        client.get("/organization/announcements", headers={"Host": HOST}).status_code
        == 302
    )
    for blocked in (resident, manager):
        _login(client, blocked)
        assert (
            client.get(
                "/organization/announcements", headers={"Host": HOST}
            ).status_code
            == 403
        )
        client.post("/auth/logout", headers={"Host": HOST})
    _login(client, admin)
    response = client.get("/organization/announcements", headers={"Host": HOST})
    assert response.status_code == 200
    assert b"Gizli Duyuru" not in response.data
    assert (
        client.get(
            f"/organization/announcements/{hidden.id}",
            headers={"Host": HOST},
        ).status_code
        == 404
    )
    detail = client.get(
        f"/organization/announcements/{safe.id}", headers={"Host": HOST}
    )
    assert b"&lt;script&gt;" in detail.data
    assert b"<script>" not in detail.data
    assert b"onerror=alert(1)&gt;" in detail.data


def test_resident_routes_hide_non_visible_and_cross_tenant(
    client: FlaskClient,
) -> None:
    organization, admin, first, _ = _scope()
    resident = _resident_in_building(
        organization, first, "resident-route@example.com"
    )
    visible = create_announcement(
        db.session,
        organization_id=organization.id,
        created_by_user_id=admin.id,
        title="Resident Görür",
        body="Görünür içerik.",
        audience_scope=AnnouncementAudienceScope.ORGANIZATION,
        publish_at=utc_now() - timedelta(minutes=1),
    )
    hidden = create_announcement(
        db.session,
        organization_id=organization.id,
        created_by_user_id=admin.id,
        title="Resident Göremez",
        body="Taslak içerik.",
        audience_scope=AnnouncementAudienceScope.ORGANIZATION,
    )
    db.session.commit()
    _session_login(client, resident)
    listing = client.get("/resident/announcements", headers={"Host": HOST})
    assert listing.status_code == 200
    assert b"Resident G\xc3\xb6r\xc3\xbcr" in listing.data
    assert b"Resident G\xc3\xb6remez" not in listing.data
    assert b'data-view-toggle="announcements"' in listing.data
    assert b'data-view-list="announcements"' in listing.data
    assert (
        client.get(
            f"/resident/announcements/{visible.id}", headers={"Host": HOST}
        ).status_code
        == 200
    )
    assert (
        client.get(
            f"/resident/announcements/{hidden.id}", headers={"Host": HOST}
        ).status_code
        == 404
    )


def test_organization_create_route_validates_targets_and_csrf(
    app: Flask,
    client: FlaskClient,
) -> None:
    organization, admin, first, _ = _scope()
    other = _organization("form-other", "form-other.example.com")
    hidden = _building(other, "FORM-GİZLİ")
    db.session.commit()
    _login(client, admin)
    invalid = client.post(
        "/organization/announcements",
        headers={"Host": HOST},
        data={
            "title": "Geçersiz bina",
            "body": "Başka tenant hedefi.",
            "audience_scope": "buildings",
            "building_ids": [str(hidden.id)],
            "publication_mode": "draft",
        },
    )
    assert invalid.status_code == 400
    assert (
        db.session.scalar(
            select(Announcement).where(
                Announcement.organization_id == organization.id,
                Announcement.title == "Geçersiz bina",
            )
        )
        is None
    )

    app.config["WTF_CSRF_ENABLED"] = True
    assert (
        client.post(
            "/organization/announcements",
            headers={"Host": HOST},
            data={
                "title": "CSRF olmadan",
                "body": "Kaydedilmemeli.",
                "audience_scope": "buildings",
                "building_ids": [str(first.id)],
                "publication_mode": "draft",
            },
        ).status_code
        == 400
    )
    form_page = client.get(
        "/organization/announcements/new", headers={"Host": HOST}
    )
    token_match = re.search(
        rb'name="csrf_token"[^>]*value="([^"]+)"', form_page.data
    )
    assert token_match is not None
    created = client.post(
        "/organization/announcements",
        headers={"Host": HOST},
        data={
            "csrf_token": token_match.group(1).decode(),
            "title": "Güvenli Duyuru",
            "body": "Form ve CSRF doğrulandı.",
            "audience_scope": "buildings",
            "building_ids": [str(first.id)],
            "publication_mode": "draft",
        },
    )
    assert created.status_code == 302
    listing = client.get(
        f"/organization/announcements?building_id={first.id}",
        headers={"Host": HOST},
    )
    assert listing.status_code == 200
    assert "Güvenli Duyuru".encode() in listing.data
    assert first.name.encode() in listing.data
    assert b">Bina<" in listing.data
    assert b">Hedef<" not in listing.data
    assert b">Arama<" not in listing.data
    assert (
        client.get(
            f"/organization/announcements?building_id={hidden.id}",
            headers={"Host": HOST},
        ).status_code
        == 404
    )


def test_organization_mutation_routes_cover_edit_publish_archive_and_idor(
    client: FlaskClient,
) -> None:
    organization, admin, first, _ = _scope()
    draft = create_announcement(
        db.session,
        organization_id=organization.id,
        created_by_user_id=admin.id,
        title="Route Taslağı",
        body="İlk metin.",
        audience_scope=AnnouncementAudienceScope.BUILDINGS,
        building_ids=(first.id,),
    )
    other = _organization("mutation-other", "mutation-other.example.com")
    other_admin = _user("mutation-other-admin@example.com")
    _membership(other, other_admin, OrganizationMembershipRole.ORGANIZATION_ADMIN)
    hidden = create_announcement(
        db.session,
        organization_id=other.id,
        created_by_user_id=other_admin.id,
        title="Başka tenant",
        body="Gizli.",
        audience_scope=AnnouncementAudienceScope.ORGANIZATION,
    )
    db.session.commit()
    _login(client, admin)

    edit_page = client.get(
        f"/organization/announcements/{draft.id}/edit",
        headers={"Host": HOST},
    )
    assert edit_page.status_code == 200
    edited = client.post(
        f"/organization/announcements/{draft.id}/edit",
        headers={"Host": HOST},
        data={
            "title": "Route Taslağı Güncellendi",
            "body": "Yeni metin.",
            "audience_scope": "organization",
            "publication_mode": "draft",
        },
    )
    assert edited.status_code == 302
    published = client.post(
        f"/organization/announcements/{draft.id}/publish",
        headers={"Host": HOST},
    )
    assert published.status_code == 302
    persisted = db.session.get(Announcement, draft.id)
    assert persisted is not None
    assert persisted.status is AnnouncementStatus.PUBLISHED
    assert (
        client.get(
            f"/organization/announcements/{draft.id}/edit",
            headers={"Host": HOST},
        ).status_code
        == 400
    )
    archived = client.post(
        f"/organization/announcements/{draft.id}/archive",
        headers={"Host": HOST},
    )
    assert archived.status_code == 302
    persisted = db.session.get(Announcement, draft.id)
    assert persisted is not None
    assert persisted.status is AnnouncementStatus.ARCHIVED
    assert (
        client.post(
            f"/organization/announcements/{hidden.id}/publish",
            headers={"Host": HOST},
        ).status_code
        == 404
    )


def test_list_search_filters_pagination_and_query_budget() -> None:
    organization, admin, _, _ = _scope()
    now = utc_now()
    for index in range(25):
        create_announcement(
            db.session,
            organization_id=organization.id,
            created_by_user_id=admin.id,
            title=f"Bakım {index:02d}",
            body="Asansör bakım duyurusu.",
            audience_scope=AnnouncementAudienceScope.ORGANIZATION,
            publish_at=now - timedelta(minutes=index),
        )
    db.session.commit()
    queries: list[str] = []

    def _count(
        _connection: object,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _executemany: object,
    ) -> None:
        queries.append(statement)

    event.listen(db.engine, "before_cursor_execute", _count)
    try:
        listing = list_organization_announcements(
            db.session,
            organization_id=organization.id,
            search="BAK",
            status_filter="published",
            audience_filter="organization",
            sort="title",
            direction="asc",
            page=2,
            per_page=20,
        )
    finally:
        event.remove(db.engine, "before_cursor_execute", _count)
    assert listing.total == 25
    assert len(listing.items) == 5
    assert len(queries) <= 5
    assert [item.title for item in listing.items] == [
        f"Bakım {index:02d}" for index in range(20, 25)
    ]

    resident = _user("budget-resident@example.com")
    _membership(
        organization, resident, OrganizationMembershipRole.ORGANIZATION_MEMBER
    )
    db.session.commit()
    queries.clear()
    event.listen(db.engine, "before_cursor_execute", _count)
    try:
        resident_listing = list_resident_announcements(
            db.session,
            organization_id=organization.id,
            user_id=resident.id,
            page=1,
            per_page=20,
            now=now,
        )
    finally:
        event.remove(db.engine, "before_cursor_execute", _count)
    assert resident_listing.total == 25
    assert len(queries) <= 5


def test_read_receipt_is_user_scoped_idempotent_and_historical() -> None:
    organization, admin, first, _ = _scope()
    resident = _resident_in_building(
        organization, first, "receipt-resident@example.com"
    )
    second_resident = _resident_in_building(
        organization, first, "receipt-second@example.com"
    )
    now = utc_now()
    announcement = create_announcement(
        db.session,
        organization_id=organization.id,
        created_by_user_id=admin.id,
        title="Okuma Kaydı",
        body="Kullanıcı bazlı receipt.",
        audience_scope=AnnouncementAudienceScope.ORGANIZATION,
        publish_at=now - timedelta(minutes=1),
    )
    other_announcement = create_announcement(
        db.session,
        organization_id=organization.id,
        created_by_user_id=admin.id,
        title="İkinci Duyuru",
        body="Aynı kullanıcı bunu da okuyabilir.",
        audience_scope=AnnouncementAudienceScope.ORGANIZATION,
        publish_at=now - timedelta(minutes=1),
    )
    first_read = mark_announcement_read(
        db.session,
        organization_id=organization.id,
        user_id=resident.id,
        announcement_id=announcement.id,
        read_at=now,
    )
    repeated = mark_announcement_read(
        db.session,
        organization_id=organization.id,
        user_id=resident.id,
        announcement_id=announcement.id,
        read_at=now + timedelta(minutes=5),
    )
    assert repeated.id == first_read.id
    assert repeated.read_at == first_read.read_at
    second_user_read = mark_announcement_read(
        db.session,
        organization_id=organization.id,
        user_id=second_resident.id,
        announcement_id=announcement.id,
        read_at=now,
    )
    second_announcement_read = mark_announcement_read(
        db.session,
        organization_id=organization.id,
        user_id=resident.id,
        announcement_id=other_announcement.id,
        read_at=now,
    )
    assert second_user_read.id != first_read.id
    assert second_announcement_read.id != first_read.id
    assert (
        get_announcement_read_state(
            db.session,
            organization_id=organization.id,
            user_id=resident.id,
            announcement_id=announcement.id,
            now=now,
        ).is_read
        is True
    )
    archive_announcement(
        db.session,
        organization_id=organization.id,
        announcement_id=announcement.id,
    )
    db.session.commit()
    assert (
        db.session.scalar(
            select(AnnouncementRead).where(
                AnnouncementRead.announcement_id == announcement.id,
                AnnouncementRead.user_id == resident.id,
            )
        )
        is not None
    )
    db.session.add(
        AnnouncementRead(
            organization_id=organization.id,
            announcement_id=announcement.id,
            user_id=resident.id,
            read_at=now + timedelta(hours=1),
        )
    )
    with pytest.raises(IntegrityError):
        db.session.flush()
    db.session.rollback()


def test_read_receipt_rejects_non_visible_and_cross_tenant_announcements() -> None:
    organization, admin, first, second = _scope()
    resident = _resident_in_building(
        organization, first, "receipt-scope@example.com"
    )
    now = utc_now()
    cases = [
        create_announcement(
            db.session,
            organization_id=organization.id,
            created_by_user_id=admin.id,
            title="Taslak Receipt",
            body="Görünmez.",
            audience_scope=AnnouncementAudienceScope.ORGANIZATION,
        ),
        create_announcement(
            db.session,
            organization_id=organization.id,
            created_by_user_id=admin.id,
            title="Gelecek Receipt",
            body="Henüz görünmez.",
            audience_scope=AnnouncementAudienceScope.ORGANIZATION,
            publish_at=now + timedelta(days=1),
        ),
        create_announcement(
            db.session,
            organization_id=organization.id,
            created_by_user_id=admin.id,
            title="Süresi Dolmuş Receipt",
            body="Artık görünmez.",
            audience_scope=AnnouncementAudienceScope.ORGANIZATION,
            publish_at=now - timedelta(days=2),
            expires_at=now - timedelta(days=1),
        ),
        create_announcement(
            db.session,
            organization_id=organization.id,
            created_by_user_id=admin.id,
            title="Hedef Dışı Receipt",
            body="Başka binaya ait.",
            audience_scope=AnnouncementAudienceScope.BUILDINGS,
            building_ids=(second.id,),
            publish_at=now - timedelta(minutes=1),
        ),
    ]
    archived = create_announcement(
        db.session,
        organization_id=organization.id,
        created_by_user_id=admin.id,
        title="Arşiv Receipt",
        body="Arşivlendi.",
        audience_scope=AnnouncementAudienceScope.ORGANIZATION,
        publish_at=now - timedelta(minutes=1),
    )
    archive_announcement(
        db.session,
        organization_id=organization.id,
        announcement_id=archived.id,
    )
    cases.append(archived)
    other = _organization("receipt-other", "receipt-other.example.com")
    other_admin = _user("receipt-other-admin@example.com")
    _membership(other, other_admin, OrganizationMembershipRole.ORGANIZATION_ADMIN)
    cases.append(
        create_announcement(
            db.session,
            organization_id=other.id,
            created_by_user_id=other_admin.id,
            title="Cross Tenant Receipt",
            body="Başka tenant.",
            audience_scope=AnnouncementAudienceScope.ORGANIZATION,
            publish_at=now - timedelta(minutes=1),
        )
    )
    for item in cases:
        with pytest.raises(EntityNotFoundError):
            mark_announcement_read(
                db.session,
                organization_id=organization.id,
                user_id=resident.id,
                announcement_id=item.id,
                read_at=now,
            )


def test_notification_center_filters_sorting_and_unread_count() -> None:
    organization, admin, first, second = _scope()
    resident = _resident_in_building(
        organization, first, "notification-resident@example.com"
    )
    now = utc_now()
    older = create_announcement(
        db.session,
        organization_id=organization.id,
        created_by_user_id=admin.id,
        title="Eski Genel",
        body="Okunacak.",
        audience_scope=AnnouncementAudienceScope.ORGANIZATION,
        publish_at=now - timedelta(hours=2),
    )
    newer = create_announcement(
        db.session,
        organization_id=organization.id,
        created_by_user_id=admin.id,
        title="Yeni Bina",
        body="Okunmamış kalacak.",
        audience_scope=AnnouncementAudienceScope.BUILDINGS,
        building_ids=(first.id,),
        publish_at=now - timedelta(hours=1),
    )
    create_announcement(
        db.session,
        organization_id=organization.id,
        created_by_user_id=admin.id,
        title="Bağlı Olmayan Bina",
        body="Listelenmez.",
        audience_scope=AnnouncementAudienceScope.BUILDINGS,
        building_ids=(second.id,),
        publish_at=now - timedelta(minutes=30),
    )
    mark_announcement_read(
        db.session,
        organization_id=organization.id,
        user_id=resident.id,
        announcement_id=older.id,
        read_at=now,
    )
    db.session.commit()
    listing = list_resident_notifications(
        db.session,
        organization_id=organization.id,
        user_id=resident.id,
        now=now,
    )
    assert [item.title for item in listing.items] == ["Yeni Bina", "Eski Genel"]
    assert [item.is_read for item in listing.items] == [False, True]
    assert [
        item.title
        for item in list_resident_notifications(
            db.session,
            organization_id=organization.id,
            user_id=resident.id,
            state_filter="unread",
            now=now,
        ).items
    ] == ["Yeni Bina"]
    assert [
        item.title
        for item in list_resident_notifications(
            db.session,
            organization_id=organization.id,
            user_id=resident.id,
            state_filter="read",
            now=now,
        ).items
    ] == ["Eski Genel"]
    assert (
        get_unread_announcement_count(
            db.session,
            organization_id=organization.id,
            user_id=resident.id,
            now=now,
        )
        == 1
    )
    assert newer.id == listing.items[0].announcement_id


def test_organization_engagement_uses_dynamic_distinct_residents() -> None:
    organization, admin, first, second = _scope()
    first_resident = _resident_in_building(
        organization, first, "metric-first@example.com"
    )
    second_resident = _resident_in_building(
        organization, second, "metric-second@example.com"
    )
    inactive = _resident_in_building(
        organization, first, "metric-inactive@example.com"
    )
    inactive.status = UserStatus.INACTIVE
    duplicate_apartment = Apartment(
        organization_id=organization.id,
        building_id=second.id,
        number="DUP",
        unit_code="DUP",
    )
    db.session.add(duplicate_apartment)
    db.session.flush()
    db.session.add(
        ApartmentMembership(
            organization_id=organization.id,
            apartment_id=duplicate_apartment.id,
            user_id=first_resident.id,
            role=ApartmentMembershipRole.RESIDENT,
            starts_at=utc_now() - timedelta(days=1),
        )
    )
    now = utc_now()
    organization_announcement = create_announcement(
        db.session,
        organization_id=organization.id,
        created_by_user_id=admin.id,
        title="Organization Metriği",
        body="İki aktif resident.",
        audience_scope=AnnouncementAudienceScope.ORGANIZATION,
        publish_at=now - timedelta(minutes=1),
    )
    building_announcement = create_announcement(
        db.session,
        organization_id=organization.id,
        created_by_user_id=admin.id,
        title="Bina Metriği",
        body="İki hedef, distinct kullanıcı.",
        audience_scope=AnnouncementAudienceScope.BUILDINGS,
        building_ids=(first.id, second.id),
        publish_at=now - timedelta(minutes=1),
    )
    mark_announcement_read(
        db.session,
        organization_id=organization.id,
        user_id=first_resident.id,
        announcement_id=organization_announcement.id,
        read_at=now,
    )
    mark_announcement_read(
        db.session,
        organization_id=organization.id,
        user_id=first_resident.id,
        announcement_id=building_announcement.id,
        read_at=now,
    )
    db.session.commit()
    organization_detail = get_organization_announcement(
        db.session,
        organization_id=organization.id,
        announcement_id=organization_announcement.id,
        now=now,
    )
    assert organization_detail.engagement.reachable_resident_count == 2
    assert organization_detail.engagement.read_resident_count == 1
    assert organization_detail.engagement.unread_resident_count == 1
    assert str(organization_detail.engagement.read_rate) == "50.0"
    building_detail = get_organization_announcement(
        db.session,
        organization_id=organization.id,
        announcement_id=building_announcement.id,
        now=now,
    )
    assert building_detail.engagement.reachable_resident_count == 2
    assert building_detail.engagement.read_resident_count == 1

    second_membership = db.session.scalar(
        select(OrganizationMembership).where(
            OrganizationMembership.organization_id == organization.id,
            OrganizationMembership.user_id == second_resident.id,
        )
    )
    assert second_membership is not None
    mark_announcement_read(
        db.session,
        organization_id=organization.id,
        user_id=second_resident.id,
        announcement_id=organization_announcement.id,
        read_at=now,
    )
    second_membership.is_active = False
    db.session.commit()
    historical = get_organization_announcement(
        db.session,
        organization_id=organization.id,
        announcement_id=organization_announcement.id,
        now=now,
    ).engagement
    assert historical.reachable_resident_count == 1
    assert historical.read_resident_count == 2
    assert historical.unread_resident_count == 0
    assert str(historical.read_rate) == "100.0"


def test_resident_detail_and_manual_read_routes_are_idempotent_and_protected(
    app: Flask,
    client: FlaskClient,
) -> None:
    organization, admin, first, _ = _scope()
    resident = _resident_in_building(
        organization, first, "notification-route@example.com"
    )
    first_announcement = create_announcement(
        db.session,
        organization_id=organization.id,
        created_by_user_id=admin.id,
        title="Detayda Okundu",
        body="GET detay receipt üretir.",
        audience_scope=AnnouncementAudienceScope.ORGANIZATION,
        publish_at=utc_now() - timedelta(minutes=1),
    )
    second_announcement = create_announcement(
        db.session,
        organization_id=organization.id,
        created_by_user_id=admin.id,
        title="Manuel Okundu",
        body="POST receipt üretir.",
        audience_scope=AnnouncementAudienceScope.ORGANIZATION,
        publish_at=utc_now() - timedelta(minutes=1),
    )
    db.session.commit()
    _login(client, resident)
    detail = client.get(
        f"/resident/announcements/{first_announcement.id}",
        headers={"Host": HOST},
    )
    assert detail.status_code == 200
    first_receipt = db.session.scalar(
        select(AnnouncementRead).where(
            AnnouncementRead.announcement_id == first_announcement.id,
            AnnouncementRead.user_id == resident.id,
        )
    )
    assert first_receipt is not None
    first_read_at = first_receipt.read_at
    assert (
        client.get(
            f"/resident/announcements/{first_announcement.id}",
            headers={"Host": HOST},
        ).status_code
        == 200
    )
    db.session.refresh(first_receipt)
    assert first_receipt.read_at == first_read_at
    center = client.get("/resident/notifications", headers={"Host": HOST})
    assert center.status_code == 200
    assert b"notification-count" in center.data

    app.config["WTF_CSRF_ENABLED"] = True
    assert (
        client.post(
            f"/resident/notifications/{second_announcement.id}/read",
            headers={"Host": HOST},
        ).status_code
        == 400
    )
    center = client.get("/resident/notifications", headers={"Host": HOST})
    token = re.search(
        rb'name="csrf_token"[^>]*value="([^"]+)"', center.data
    )
    assert token is not None
    marked = client.post(
        f"/resident/notifications/{second_announcement.id}/read",
        headers={"Host": HOST},
        data={
            "csrf_token": token.group(1).decode(),
            "user_id": str(admin.id),
            "next": "https://evil.example/",
        },
    )
    assert marked.status_code == 302
    assert marked.headers["Location"].endswith("/resident/notifications")
    receipt = db.session.scalar(
        select(AnnouncementRead).where(
            AnnouncementRead.announcement_id == second_announcement.id,
        )
    )
    assert receipt is not None
    assert receipt.user_id == resident.id
    app.config["WTF_CSRF_ENABLED"] = False
    client.post("/auth/logout", headers={"Host": HOST})
    _login(client, admin)
    assert (
        client.post(
            f"/resident/notifications/{second_announcement.id}/read",
            headers={"Host": HOST},
        ).status_code
        == 403
    )


def test_notification_and_engagement_query_budgets() -> None:
    organization, admin, first, _ = _scope()
    resident = _resident_in_building(
        organization, first, "notification-budget@example.com"
    )
    now = utc_now()
    announcement_ids = []
    for index in range(30):
        item = create_announcement(
            db.session,
            organization_id=organization.id,
            created_by_user_id=admin.id,
            title=f"Bildirim {index:02d}",
            body="Sabit sorgu bütçesi.",
            audience_scope=AnnouncementAudienceScope.ORGANIZATION,
            publish_at=now - timedelta(minutes=index + 1),
        )
        announcement_ids.append(item.id)
    db.session.commit()
    queries: list[str] = []

    def _count(
        _connection: object,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _executemany: object,
    ) -> None:
        queries.append(statement)

    organization_id = organization.id
    resident_id = resident.id
    announcement_id = announcement_ids[0]
    event.listen(db.engine, "before_cursor_execute", _count)
    try:
        listing = list_resident_notifications(
            db.session,
            organization_id=organization_id,
            user_id=resident_id,
            now=now,
        )
    finally:
        event.remove(db.engine, "before_cursor_execute", _count)
    assert listing.total == 30
    assert len(queries) <= 2

    queries.clear()
    event.listen(db.engine, "before_cursor_execute", _count)
    try:
        assert (
            get_unread_announcement_count(
                db.session,
                organization_id=organization_id,
                user_id=resident_id,
                now=now,
            )
            == 30
        )
    finally:
        event.remove(db.engine, "before_cursor_execute", _count)
    assert len(queries) == 1

    queries.clear()
    event.listen(db.engine, "before_cursor_execute", _count)
    try:
        detail = get_organization_announcement(
            db.session,
            organization_id=organization_id,
            announcement_id=announcement_id,
            now=now,
        )
    finally:
        event.remove(db.engine, "before_cursor_execute", _count)
    assert detail.engagement.reachable_resident_count == 1
    assert len(queries) <= 8


def test_unread_context_runs_once_only_for_resident_requests(
    client: FlaskClient,
) -> None:
    organization, admin, first, _ = _scope()
    resident = _resident_in_building(
        organization, first, "navbar-count@example.com"
    )
    create_announcement(
        db.session,
        organization_id=organization.id,
        created_by_user_id=admin.id,
        title="Navbar Rozeti",
        body="Bir kez sayılmalı.",
        audience_scope=AnnouncementAudienceScope.ORGANIZATION,
        publish_at=utc_now() - timedelta(minutes=1),
    )
    db.session.commit()
    statements: list[str] = []

    def _capture(
        _connection: object,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _executemany: object,
    ) -> None:
        statements.append(statement)

    _login(client, resident)
    event.listen(db.engine, "before_cursor_execute", _capture)
    try:
        response = client.get("/resident/", headers={"Host": HOST})
    finally:
        event.remove(db.engine, "before_cursor_execute", _capture)
    assert response.status_code == 200
    assert sum("announcement_reads" in item for item in statements) == 1

    client.post("/auth/logout", headers={"Host": HOST})
    _login(client, admin)
    statements.clear()
    event.listen(db.engine, "before_cursor_execute", _capture)
    try:
        response = client.get("/organization/", headers={"Host": HOST})
    finally:
        event.remove(db.engine, "before_cursor_execute", _capture)
    assert response.status_code == 200
    assert not any("announcement_reads" in item for item in statements)
