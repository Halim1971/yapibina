from flask_sqlalchemy.session import Session as FlaskSession
from sqlalchemy.orm import Session, scoped_session

SessionLike = Session | scoped_session[FlaskSession]


class ServiceValidationError(ValueError):
    pass


class EntityNotFoundError(ServiceValidationError):
    pass


class TenantBoundaryError(ServiceValidationError):
    pass


class MembershipOverlapError(ServiceValidationError):
    pass


class DuplicateEntityError(ServiceValidationError):
    pass


class InvalidStateTransitionError(ServiceValidationError):
    pass


__all__ = [
    "EntityNotFoundError",
    "DuplicateEntityError",
    "InvalidStateTransitionError",
    "MembershipOverlapError",
    "ServiceValidationError",
    "SessionLike",
    "TenantBoundaryError",
]
