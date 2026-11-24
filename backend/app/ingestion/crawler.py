"""Same-domain crawl discovery (docs/03-TRD.md: "capped same-domain crawl
and sitemap page selection"). Tries sitemap.xml / sitemap_index.xml first
since it's authoritative and cheap; falls back to bounded same-domain
link-following from the homepage when no sitemap exists. Every fetch goes
through the SSRF-hardened client, every candidate URL is independently
SSRF-validated, and robots.txt is respected throughout.
"""
import urllib.robotparser
from urllib.parse import urljoin, urlparse
from xml.etree import ElementTree

from bs4 import BeautifulSoup

from app.security.ssrf_http import SSRFBlocked, fetch, validate_url

SITEMAP_PATHS = ("/sitemap.xml", "/sitemap_index.xml")
_SITEMAP_NAMESPACE = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}


class CrawlError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _same_domain(url: str, root_netloc: str) -> bool:
    return urlparse(url).netloc == root_netloc


def _load_robots(root_url: str) -> urllib.robotparser.RobotFileParser:
    """Missing or unparsable robots.txt is treated as "allow everything",
    matching standard crawler behavior -- a 404 on /robots.txt is not a
    site owner opting out of anything."""
    parser = urllib.robotparser.RobotFileParser()
    robots_url = urljoin(root_url, "/robots.txt")
    try:
        validate_url(robots_url)
        response = fetch(robots_url)
        parser.parse(response.text.splitlines())
    except Exception:  # noqa: BLE001 -- any fetch/parse failure here means "no restrictions found"
        parser.allow_all = True
    return parser


def _try_sitemap(root_url: str, root_netloc: str, max_pages: int) -> list[str] | None:
    """Returns same-domain URLs from the first parsable sitemap found, or
    None if no sitemap exists / none of its URLs are same-domain."""
    for path in SITEMAP_PATHS:
        sitemap_url = urljoin(root_url, path)
        try:
            validate_url(sitemap_url)
            response = fetch(sitemap_url)
        except Exception:  # noqa: BLE001 -- SSRFBlocked, timeout, 404, etc. -- try the next candidate path
            continue

        try:
            root = ElementTree.fromstring(response.content)
        except ElementTree.ParseError:
            continue

        locs = [el.text.strip() for el in root.findall(".//sm:loc", _SITEMAP_NAMESPACE) if el.text]
        if not locs:
            locs = [el.text.strip() for el in root.findall(".//loc") if el.text]  # tolerate missing namespace

        same_domain_locs = [u for u in locs if _same_domain(u, root_netloc)]
        if same_domain_locs:
            return same_domain_locs[:max_pages]

    return None


def _crawl_links(root_url: str, root_netloc: str, max_pages: int, robots: urllib.robotparser.RobotFileParser) -> list[str]:
    """Breadth-first same-domain link following, bounded by max_pages. A
    single unreachable page is skipped, not fatal to the whole crawl."""
    discovered: list[str] = []
    seen: set[str] = {root_url}
    queue = [root_url]

    while queue and len(discovered) < max_pages:
        url = queue.pop(0)

        if not robots.can_fetch("*", url):
            continue

        try:
            validate_url(url)
            response = fetch(url)
        except Exception:  # noqa: BLE001 -- skip unreachable pages, keep crawling the rest
            continue

        discovered.append(url)
        if len(discovered) >= max_pages:
            break

        try:
            soup = BeautifulSoup(response.text, "html.parser")
        except Exception:  # noqa: BLE001 -- not parsable HTML, nothing to extract links from
            continue

        for a_tag in soup.find_all("a", href=True):
            next_url = urljoin(url, a_tag["href"]).split("#")[0]
            if _same_domain(next_url, root_netloc) and next_url not in seen:
                seen.add(next_url)
                queue.append(next_url)

    return discovered


def discover_pages(root_url: str, max_pages: int) -> list[str]:
    """Returns a capped, same-domain, robots-respecting list of page URLs
    reachable from root_url -- via sitemap.xml/sitemap_index.xml when
    available, otherwise via bounded same-domain link-following from the
    homepage."""
    try:
        validate_url(root_url)
    except SSRFBlocked as exc:
        raise CrawlError(exc.code, exc.message) from exc

    root_netloc = urlparse(root_url).netloc
    robots = _load_robots(root_url)

    if not robots.can_fetch("*", root_url):
        raise CrawlError("robots_disallowed", "robots.txt disallows crawling this site.")

    sitemap_urls = _try_sitemap(root_url, root_netloc, max_pages)
    if sitemap_urls:
        allowed = [u for u in sitemap_urls if robots.can_fetch("*", u)][:max_pages]
        if allowed:
            return allowed

    return _crawl_links(root_url, root_netloc, max_pages, robots)
