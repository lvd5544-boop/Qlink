from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SPEC = spec_from_file_location("production_smoke", ROOT / "scripts" / "production_smoke.py")
assert SPEC and SPEC.loader
smoke = module_from_spec(SPEC)
SPEC.loader.exec_module(smoke)


def test_ready_contract_rejects_internal_names_or_extra_checks():
    safe = {
        "status": "ready",
        "model_mode": "rules_only",
        "checks": {"model": {"ok": True, "reason": "configuration_missing"}},
    }
    assert smoke.validate_ready(safe, str(safe)) == []

    unsafe = {
        "status": "ready",
        "checks": {"model": {"reason": "api_key_missing"}, "database": {"ok": True}},
    }
    errors = smoke.validate_ready(unsafe, str(unsafe))
    assert any("unexpected checks" in error for error in errors)
    assert any("internal configuration" in error for error in errors)


def test_security_header_contract_requires_no_store_and_frame_denial():
    headers = {
        "Cache-Control": "private, no-store",
        "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Referrer-Policy": "no-referrer",
    }
    assert smoke.validate_headers(headers, smoke.REQUIRED_API_HEADERS, api=True) == []

    errors = smoke.validate_headers({}, smoke.REQUIRED_API_HEADERS, api=True)
    assert any("cache-control" in error for error in errors)
    assert any("no-store" in error for error in errors)


def test_redirect_must_keep_domain_and_upgrade_to_https():
    assert smoke.validate_redirect(308, "https://jobs.qlink.cn/", "jobs.qlink.cn") == []
    assert smoke.validate_redirect(200, "", "jobs.qlink.cn")
    assert smoke.validate_redirect(308, "https://evil.example/", "jobs.qlink.cn")
