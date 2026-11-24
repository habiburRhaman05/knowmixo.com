"""Contract gate: every route in docs/16-API-ROUTES.md must be registered by
the app (docs/19 Phase 8: "OpenAPI contract generation"). Parses the doc
tables so the check can't drift from the written spec."""
import re
from pathlib import Path

DOC = Path(__file__).resolve().parents[3] / "docs" / "16-API-ROUTES.md"

def _spec_routes() -> set[tuple[str, str]]:
    routes = set()
    for line in DOC.read_text(encoding="utf-8").splitlines():
        m = re.match(r"\|\s*(GET|POST|PUT|PATCH|DELETE)\s*\|\s*(/[^\s|]*)\s*\|", line)
        if not m:
            continue
        method, path = m.group(1), m.group(2)
        if path.startswith("/health"):
            routes.add((method, path))
        else:
            routes.add((method, "/api/v1" + path))
    return routes


def _app_routes() -> set[tuple[str, str]]:
    from app.main import app

    found = set()
    for r in app.routes:
        for method in getattr(r, "methods", None) or ():
            found.add((method, re.sub(r"\{[^}]+\}", "{}", r.path)))
    return found


def _normalise(routes):
    return {(m, re.sub(r"\{[^}]+\}", "{}", p)) for m, p in routes}


def test_doc_parses_a_meaningful_number_of_routes():
    assert len(_spec_routes()) >= 55


def test_every_documented_route_is_implemented():
    missing = sorted(_normalise(_spec_routes()) - _app_routes())
    assert not missing, f"documented but not implemented: {missing}"


def test_no_legacy_demo_routes_are_reachable():
    paths = {p for _m, p in _app_routes()}
    for legacy in ("/api/chat", "/api/feedback", "/public/v1/chat"):
        assert legacy not in paths
    assert not any(p.startswith("/api/admin") or p.startswith("/api/approvals") for p in paths)
