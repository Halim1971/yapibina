from enum import Enum


class StringEnum(str, Enum):
    pass


class UserStatus(StringEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    LOCKED = "locked"


class OrganizationStatus(StringEnum):
    PENDING = "pending"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    CLOSED = "closed"


class OrganizationMembershipRole(StringEnum):
    ORGANIZATION_ADMIN = "organization_admin"
    ORGANIZATION_MEMBER = "organization_member"


class BuildingMembershipRole(StringEnum):
    BUILDING_MANAGER = "building_manager"
    BUILDING_STAFF = "building_staff"


class ApartmentMembershipRole(StringEnum):
    OWNER = "owner"
    TENANT = "tenant"
    RESIDENT = "resident"
    AUTHORIZED_PERSON = "authorized_person"


class DomainType(StringEnum):
    PLATFORM_SUBDOMAIN = "platform_subdomain"
    CUSTOM_DOMAIN = "custom_domain"


class DomainState(StringEnum):
    PENDING = "pending"
    AWAITING_DNS = "awaiting_dns"
    DNS_VERIFIED = "dns_verified"
    SSL_PENDING = "ssl_pending"
    ACTIVE = "active"
    FAILED = "failed"
    SUSPENDED = "suspended"


class ChargeBatchStatus(StringEnum):
    DRAFT = "draft"
    POSTED = "posted"
    CANCELLED = "cancelled"


class ChargeType(StringEnum):
    MONTHLY_DUE = "monthly_due"
    ADDITIONAL_DUE = "additional_due"
    MANUAL = "manual"


class ChargeStatus(StringEnum):
    DRAFT = "draft"
    POSTED = "posted"
    REVERSED = "reversed"


class PaymentMethod(StringEnum):
    CASH = "cash"
    BANK_TRANSFER = "bank_transfer"
    CARD = "card"
    OTHER = "other"


class PaymentStatus(StringEnum):
    POSTED = "posted"
    REVERSED = "reversed"
