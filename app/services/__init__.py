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


class FinancialOperationError(ServiceValidationError):
    pass


class InvalidAmountError(FinancialOperationError):
    pass


class CrossTenantFinancialOperationError(FinancialOperationError):
    pass


class InvalidFinancialStateTransitionError(FinancialOperationError):
    pass


class PaymentOverAllocationError(FinancialOperationError):
    pass


class ChargeOverAllocationError(FinancialOperationError):
    pass


class DuplicateChargeBatchError(FinancialOperationError):
    pass


class DuplicateAllocationError(FinancialOperationError):
    pass


class FinancialRecordAlreadyReversedError(FinancialOperationError):
    pass


class ChargeHasAllocationsError(FinancialOperationError):
    pass


__all__ = [
    "EntityNotFoundError",
    "DuplicateEntityError",
    "DuplicateAllocationError",
    "DuplicateChargeBatchError",
    "InvalidStateTransitionError",
    "InvalidAmountError",
    "InvalidFinancialStateTransitionError",
    "CrossTenantFinancialOperationError",
    "PaymentOverAllocationError",
    "ChargeOverAllocationError",
    "FinancialOperationError",
    "FinancialRecordAlreadyReversedError",
    "ChargeHasAllocationsError",
    "MembershipOverlapError",
    "ServiceValidationError",
    "SessionLike",
    "TenantBoundaryError",
]
