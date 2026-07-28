from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from flask_login import UserMixin
from sqlalchemy import Boolean, DateTime, String
from sqlalchemy import Enum as SQLAlchemyEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import Base, db, login_manager
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin, normalize_email
from app.models.enums import UserStatus
from app.security.password_policy import validate_password

if TYPE_CHECKING:
    from app.models.apartment import ApartmentMembership
    from app.models.building import BuildingMembership
    from app.models.membership import OrganizationMembership


class User(UUIDPrimaryKeyMixin, TimestampMixin, UserMixin, Base):  # type: ignore[misc]
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(254), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(40))
    status: Mapped[UserStatus] = mapped_column(
        SQLAlchemyEnum(
            UserStatus,
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            values_callable=lambda enum: [item.value for item in enum],
            name="user_status",
        ),
        default=UserStatus.ACTIVE,
        nullable=False,
    )
    is_platform_super_admin: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    organization_memberships: Mapped[list[OrganizationMembership]] = relationship(
        back_populates="user"
    )
    building_memberships: Mapped[list[BuildingMembership]] = relationship(
        back_populates="user"
    )
    apartment_memberships: Mapped[list[ApartmentMembership]] = relationship(
        back_populates="user"
    )

    @validates("email")
    def validate_email(self, _: str, value: str) -> str:
        return normalize_email(value)

    @property
    def is_active(self) -> bool:
        return self.status is UserStatus.ACTIVE

    def get_id(self) -> str:
        return str(self.id)

    def set_password(self, password: str) -> None:
        validate_password(password, email=self.email)
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        if not password or not self.password_hash:
            return False
        return check_password_hash(self.password_hash, password)


@login_manager.user_loader  # type: ignore[untyped-decorator]
def load_user(user_id: str) -> User | None:
    try:
        parsed_id = uuid.UUID(user_id)
    except (ValueError, TypeError, AttributeError):
        return None
    return db.session.get(User, parsed_id)
