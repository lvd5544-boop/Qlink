#!/usr/bin/env python3
"""Public, unauthenticated post-deploy smoke checks for QLink."""

from __future__ import annotations

import argparse
import json
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener, urlopen

REQUIRED_PAGE_HEADERS = {
    "strict-transport-security",
    "content-security-policy",
    "x-content-type-options",
    "x-frame-options",
    "referrer-policy",
    "permissions-policy",
}
REQUIRED_API_HEADERS = {
    "cache-control",
    "content-security-policy",
    "x-content-type-options",
    "x-frame-options",
    "referrer-policy",
}


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def normalized_headers(headers) -> dict[str, str]:
    return {str(key).lower(): str(value) for key, value in headers.items()}


def validate_ready(payload: dict, serialized: str) -> list[str]:
    errors: list[str] = []
    if payload.get("status") != "ready":
        errors.append("/api/ready did not report ready")
    checks = payload.get("checks")
    if not isinstance(checks, dict) or set(checks) != {"model"}:
        errors.append("/api/ready exposed unexpected checks")
    lowered = serialized.lower()
    if "api_key" in lowered or "secret" in lowered:
        errors.append("/api/ready exposed an internal configuration name")
    return errors


def validate_headers(headers, required: set[str], *, api: bool = False) -> list[str]:
    values = normalized_headers(headers)
    missing = sorted(required - set(values))
    errors = [f"missing response header: {name}" for name in missing]
    if api and "no-store" not in values.get("cache-control", "").lower():
        errors.append("API response Cache-Control must include no-store")
    if (
        "content-security-policy" in values
        and "frame-ancestors 'none'" not in values["content-security-policy"]
    ):
        errors.append("Content-Security-Policy must deny framing")
    return errors


def validate_redirect(status: int, location: str, domain: str) -> list[str]:
    if status not in {301, 302, 307, 308}:
        return [f"HTTP endpoint returned {status}, expected redirect"]
    target = urlparse(location)
    if target.scheme != "https" or target.hostname != domain:
        return ["HTTP redirect did not preserve the production domain over HTTPS"]
    return []


def fetch(url: str, timeout: float) -> tuple[int, object, bytes]:
    request = Request(url, headers={"User-Agent": "qlink-production-smoke/1"})
    with urlopen(request, timeout=timeout) as response:
        return response.status, response.headers, response.read()


def fetch_without_redirect(url: str, timeout: float) -> tuple[int, object]:
    opener = build_opener(NoRedirect)
    try:
        with opener.open(Request(url), timeout=timeout) as response:
            return response.status, response.headers
    except HTTPError as exc:
        return exc.code, exc.headers


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--origin", required=True)
    parser.add_argument("--timeout", type=float, default=10.0)
    args = parser.parse_args()

    origin = args.origin.rstrip("/")
    parsed = urlparse(origin)
    if parsed.scheme != "https" or not parsed.hostname or parsed.path:
        print("ERROR: --origin must be an HTTPS origin without a path")
        return 2

    errors: list[str] = []
    try:
        ready_status, ready_headers, ready_body = fetch(
            f"{origin}/api/ready", args.timeout
        )
        if ready_status != 200:
            errors.append(f"/api/ready returned HTTP {ready_status}")
        serialized = ready_body.decode("utf-8")
        errors.extend(validate_ready(json.loads(serialized), serialized))
        errors.extend(validate_headers(ready_headers, REQUIRED_API_HEADERS, api=True))

        page_status, page_headers, _ = fetch(f"{origin}/", args.timeout)
        if page_status != 200:
            errors.append(f"/ returned HTTP {page_status}")
        errors.extend(validate_headers(page_headers, REQUIRED_PAGE_HEADERS))

        redirect_status, redirect_headers = fetch_without_redirect(
            f"http://{parsed.hostname}/", args.timeout
        )
        errors.extend(
            validate_redirect(
                redirect_status,
                redirect_headers.get("Location", ""),
                parsed.hostname,
            )
        )
    except (OSError, HTTPError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        errors.append(f"public smoke request failed: {type(exc).__name__}")

    for error in errors:
        print(f"ERROR: {error}")
    if errors:
        print(f"Production smoke failed with {len(errors)} error(s).")
        return 1
    print("Production HTTPS, readiness, redirect, and security-header smoke passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
