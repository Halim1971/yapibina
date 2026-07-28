from werkzeug.exceptions import MisdirectedRequest


class UnknownTenantHost(MisdirectedRequest):
    description = "The requested hostname is not registered for an active tenant."
