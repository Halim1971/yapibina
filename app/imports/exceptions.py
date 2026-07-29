class ImporterError(RuntimeError):
    pass


class PackageValidationError(ImporterError):
    pass


class ImportConflictError(ImporterError):
    pass


class ConcurrentImportError(ImporterError):
    pass


class CriticalFinancialChangeError(ImporterError):
    pass
