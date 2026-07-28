from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from flask import Flask, current_app, g, request

from app.tenant.exceptions import UnknownTenantHost

HEALTH_ENDPOINT = "public.health"
LOCAL_HOSTNAMES = frozenset({"localhost", "127.0.0.1", "::1"})
TEST_HOSTNAMES = frozenset({"test", "test.local", "testserver"})


@dataclass(frozen=True, slots=True)
class TenantContext:
    organization_id: str
    hostname: str


class TenantHostnameLookup(Protocol):
    def resolve(self, hostname: str) -> TenantContext | None:
        """Return a tenant only for a persisted, verified and active hostname."""


class NullTenantHostnameLookup:
    def resolve(self, hostname: str) -> TenantContext | None:
        del hostname
        return None


def normalize_hostname(host: str) -> str:
    candidate = host.strip().lower()
    if candidate.startswith("["):
        closing_bracket = candidate.find("]")
        if closing_bracket == -1:
            return ""
        candidate = candidate[1:closing_bracket]
    else:
        candidate = candidate.partition(":")[0]
    return candidate.rstrip(".")


def _is_controlled_non_tenant_host(hostname: str) -> bool:
    platform_hostname = normalize_hostname(
        str(current_app.config["PLATFORM_HOSTNAME"])
    )
    if hostname == platform_hostname:
        return True

    environment = str(current_app.config["APP_ENV"])
    if environment == "development":
        return hostname in LOCAL_HOSTNAMES
    if environment == "testing":
        return hostname in LOCAL_HOSTNAMES | TEST_HOSTNAMES
    return False


def resolve_request_tenant() -> None:
    g.tenant = None
    g.is_platform_request = False

    if request.endpoint == HEALTH_ENDPOINT:
        return

    hostname = normalize_hostname(request.host)
    if not hostname:
        raise UnknownTenantHost()

    if _is_controlled_non_tenant_host(hostname):
        g.is_platform_request = True
        return

    lookup: TenantHostnameLookup = current_app.extensions["tenant_hostname_lookup"]
    tenant = lookup.resolve(hostname)
    if tenant is None:
        raise UnknownTenantHost()

    g.tenant = tenant


def register_tenant_resolution(
    app: Flask,
    lookup: TenantHostnameLookup | None = None,
) -> None:
    app.extensions["tenant_hostname_lookup"] = lookup or NullTenantHostnameLookup()
    app.before_request(resolve_request_tenant)
