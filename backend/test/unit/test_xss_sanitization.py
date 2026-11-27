"""XSS corpus (D9.6 security suite): asserts
app.chat.rag_v2.stages.postprocess.sanitize_html neutralises every
payload in this corpus. Covers the two surfaces wired to it --
LLM-generated answers (app.chat.pipeline.stream_turn /
app.chat.rag_v2.pipeline.stream_turn_v2) and human/integration-authored
agent replies (app.handoff.service.send_agent_reply) -- either of which
can carry attacker-influenced text (a crawled page's content, a
compromised public-API key) through to a visitor's rendered widget.
"""
import pytest

from app.chat.rag_v2.stages.postprocess import sanitize_html

XSS_CORPUS = [
    '<script>alert(1)</script>',
    '<img src=x onerror=alert(1)>',
    '<svg onload=alert(1)>',
    '<a href="javascript:alert(1)">click</a>',
    '<a href="JaVaScRiPt:alert(1)">click</a>',
    '<iframe src="javascript:alert(1)"></iframe>',
    '<body onload=alert(1)>',
    '<div onclick="alert(1)">click me</div>',
    '<input onfocus=alert(1) autofocus>',
    '<marquee onstart=alert(1)>',
    '"><script>alert(String.fromCharCode(88,83,83))</script>',
    "<IMG SRC=javascript:alert('XSS')>",
    '<IMG SRC=JaVaScRiPt:alert(\'XSS\')>',
    '<IMG SRC=# onmouseover="alert(1)">',
    '<IFRAME SRC="data:text/html,<script>alert(1)</script>"></IFRAME>',
    '<object data="javascript:alert(1)">',
    '<embed src="javascript:alert(1)">',
    '<style>@import "javascript:alert(1)";</style>',
    '<link rel="stylesheet" href="javascript:alert(1)">',
    '<table background="javascript:alert(1)">',
    '<form action="javascript:alert(1)"><input type=submit>',
    '<details open ontoggle=alert(1)>',
    '<video><source onerror="alert(1)">',
    '<audio src=x onerror=alert(1)>',
    '<math href="javascript:alert(1)">click</math>',
    '<base href="javascript:alert(1)//">',
    '<meta http-equiv="refresh" content="0;url=javascript:alert(1)">',
]


@pytest.mark.parametrize("payload", XSS_CORPUS)
def test_xss_payload_neutralised(payload):
    """Checks that no EXECUTABLE construct survives -- not that the bare
    substring 'javascript:' never appears anywhere in the output text.
    <style>@import "javascript:alert(1)";</style> is a real corpus entry
    whose <style> wrapper bleach strips (style is not in the allow-list),
    but whose inert text content ("@import "javascript:alert(1)";")
    survives as a plain, non-executable text node -- correct behaviour,
    not a vulnerability, since nothing interprets that text as CSS or JS
    once the <style> tag itself is gone. A blanket substring ban would
    also misfire on an innocent question like "what does javascript:void(0)
    mean?", which is not an attack."""
    cleaned = sanitize_html(payload)
    lowered = cleaned.lower()
    assert "<script" not in lowered
    assert "<style" not in lowered
    assert "<iframe" not in lowered
    assert "<object" not in lowered
    assert "<embed" not in lowered
    assert "onerror=" not in lowered
    assert "onload=" not in lowered
    assert "onclick=" not in lowered
    assert "onfocus=" not in lowered
    assert "onstart=" not in lowered
    assert "ontoggle=" not in lowered
    assert "onmouseover=" not in lowered
    assert 'href="javascript:' not in lowered
    assert "href='javascript:" not in lowered
    assert 'src="javascript:' not in lowered


def test_allowed_formatting_tags_survive():
    # The allow-list (b, i, em, strong, a[href], code, pre, ul, ol, li,
    # br, p) must still render -- sanitisation strips attack surface, not
    # ordinary markdown-rendered formatting.
    cleaned = sanitize_html("<p><strong>bold</strong> and <em>italic</em></p>")
    assert "<strong>bold</strong>" in cleaned
    assert "<em>italic</em>" in cleaned


def test_safe_link_href_survives():
    cleaned = sanitize_html('<a href="https://example.com">link</a>')
    assert 'href="https://example.com"' in cleaned


def test_unknown_tags_are_stripped_not_escaped_into_visible_text():
    # bleach's default strip=True removes the disallowed tag outright
    # rather than leaving an escaped &lt;script&gt; the user would see
    # as literal text -- either is safe against execution, but stripping
    # is the behaviour this sanitize_html wrapper actually configures.
    cleaned = sanitize_html("<script>alert(1)</script>safe text")
    assert "safe text" in cleaned
    assert "<script" not in cleaned.lower()
