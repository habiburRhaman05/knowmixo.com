"""Crawler unit tests. fetch() and validate_url() are monkeypatched to
fakes -- no real DNS/network call happens, per docs/11-AGENT-RULES.md
rule 6. SSRF validation itself is already covered by test_ssrf.py; these
tests exercise sitemap parsing, same-domain filtering, robots.txt
handling, and the link-following fallback in isolation.
"""
import pytest

from app.ingestion import crawler
from app.ingestion.crawler import CrawlError


class FakeResponse:
    def __init__(self, text: str = "", content: bytes | None = None):
        self.text = text
        self.content = content if content is not None else text.encode("utf-8")


ROOT = "https://example-test.invalid"


@pytest.fixture(autouse=True)
def no_real_validation(monkeypatch):
    """Crawler-logic tests should not depend on SSRF/DNS behavior --
    identity passthrough here, exercised separately in test_ssrf.py."""
    monkeypatch.setattr(crawler, "validate_url", lambda url: url)


def _robots_missing(url: str) -> FakeResponse:
    raise RuntimeError("404 not found")  # simulates no robots.txt present


SITEMAP_XML = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>{ROOT}/page-1</loc></url>
  <url><loc>{ROOT}/page-2</loc></url>
  <url><loc>https://other-domain.invalid/page-x</loc></url>
</urlset>
"""


def test_sitemap_discovery_returns_same_domain_urls_only(monkeypatch):
    def fake_fetch(url: str) -> FakeResponse:
        if url.endswith("/robots.txt"):
            return _robots_missing(url)
        if url.endswith("/sitemap.xml"):
            return FakeResponse(text=SITEMAP_XML)
        raise RuntimeError(f"unexpected fetch: {url}")

    monkeypatch.setattr(crawler, "fetch", fake_fetch)

    pages = crawler.discover_pages(ROOT, max_pages=20)
    assert f"{ROOT}/page-1" in pages
    assert f"{ROOT}/page-2" in pages
    assert not any("other-domain" in p for p in pages)


def test_sitemap_discovery_respects_max_pages_cap(monkeypatch):
    many_urls = "\n".join(f"<url><loc>{ROOT}/page-{i}</loc></url>" for i in range(50))
    sitemap = f'<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{many_urls}</urlset>'

    def fake_fetch(url: str) -> FakeResponse:
        if url.endswith("/robots.txt"):
            return _robots_missing(url)
        if url.endswith("/sitemap.xml"):
            return FakeResponse(text=sitemap)
        raise RuntimeError(f"unexpected fetch: {url}")

    monkeypatch.setattr(crawler, "fetch", fake_fetch)

    pages = crawler.discover_pages(ROOT, max_pages=5)
    assert len(pages) == 5


def test_falls_back_to_link_crawl_when_sitemap_missing(monkeypatch):
    homepage_html = f"""
    <html><body>
      <a href="/about">About</a>
      <a href="/pricing">Pricing</a>
      <a href="https://other-domain.invalid/hack">External</a>
    </body></html>
    """

    def fake_fetch(url: str) -> FakeResponse:
        if url.endswith("/robots.txt") or "sitemap" in url:
            raise RuntimeError("404 not found")
        if url == ROOT or url == ROOT + "/":
            return FakeResponse(text=homepage_html)
        if url in (f"{ROOT}/about", f"{ROOT}/pricing"):
            return FakeResponse(text="<html><body><p>content</p></body></html>")
        raise RuntimeError(f"unexpected fetch: {url}")

    monkeypatch.setattr(crawler, "fetch", fake_fetch)

    pages = crawler.discover_pages(ROOT, max_pages=20)
    assert ROOT in pages
    assert f"{ROOT}/about" in pages
    assert f"{ROOT}/pricing" in pages
    assert not any("other-domain" in p for p in pages)


def test_link_crawl_respects_max_pages_cap(monkeypatch):
    def fake_fetch(url: str) -> FakeResponse:
        if url.endswith("/robots.txt") or "sitemap" in url:
            raise RuntimeError("404 not found")
        # Every page links to one more page, so an uncapped crawl would run forever.
        path = url[len(ROOT):]  # e.g. "" for the root, "/page-3" for a deeper page
        page_num = int(path.rsplit("-", 1)[-1]) if path.startswith("/page-") else 0
        next_page = f"{ROOT}/page-{page_num + 1}"
        return FakeResponse(text=f'<html><body><a href="{next_page}">next</a></body></html>')

    monkeypatch.setattr(crawler, "fetch", fake_fetch)

    pages = crawler.discover_pages(ROOT, max_pages=3)
    assert len(pages) == 3


def test_robots_disallow_blocks_entire_crawl(monkeypatch):
    def fake_fetch(url: str) -> FakeResponse:
        if url.endswith("/robots.txt"):
            return FakeResponse(text="User-agent: *\nDisallow: /\n")
        raise RuntimeError(f"unexpected fetch: {url}")

    monkeypatch.setattr(crawler, "fetch", fake_fetch)

    with pytest.raises(CrawlError) as exc_info:
        crawler.discover_pages(ROOT, max_pages=20)
    assert exc_info.value.code == "robots_disallowed"


def test_robots_disallow_on_specific_path_is_skipped_during_link_crawl(monkeypatch):
    homepage_html = f'<html><body><a href="/secret">Secret</a><a href="/public">Public</a></body></html>'

    def fake_fetch(url: str) -> FakeResponse:
        if url.endswith("/robots.txt"):
            return FakeResponse(text="User-agent: *\nDisallow: /secret\n")
        if "sitemap" in url:
            raise RuntimeError("404 not found")
        if url == ROOT:
            return FakeResponse(text=homepage_html)
        if url == f"{ROOT}/public":
            return FakeResponse(text="<html><body>public content</body></html>")
        raise RuntimeError(f"unexpected fetch (should have been skipped by robots): {url}")

    monkeypatch.setattr(crawler, "fetch", fake_fetch)

    pages = crawler.discover_pages(ROOT, max_pages=20)
    assert f"{ROOT}/public" in pages
    assert f"{ROOT}/secret" not in pages


def test_single_bad_page_does_not_abort_whole_crawl(monkeypatch):
    homepage_html = f'<html><body><a href="/broken">Broken</a><a href="/good">Good</a></body></html>'

    def fake_fetch(url: str) -> FakeResponse:
        if url.endswith("/robots.txt") or "sitemap" in url:
            raise RuntimeError("404 not found")
        if url == ROOT:
            return FakeResponse(text=homepage_html)
        if url == f"{ROOT}/broken":
            raise RuntimeError("connection reset")
        if url == f"{ROOT}/good":
            return FakeResponse(text="<html><body>good content</body></html>")
        raise RuntimeError(f"unexpected fetch: {url}")

    monkeypatch.setattr(crawler, "fetch", fake_fetch)

    pages = crawler.discover_pages(ROOT, max_pages=20)
    assert f"{ROOT}/good" in pages
    assert f"{ROOT}/broken" not in pages
