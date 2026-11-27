"""SSRF validation unit tests. All targets use literal IP addresses (or
localhost) so getaddrinfo resolves purely locally -- no real DNS/network
call happens, keeping this test offline-safe per docs/11-AGENT-RULES.md
rule 6."""
import pytest

from app.security.ssrf_http import SSRFBlocked, fetch, validate_url


def test_loopback_ip_is_blocked():
    with pytest.raises(SSRFBlocked) as exc_info:
        validate_url("http://127.0.0.1/")
    assert exc_info.value.code == "private_target_blocked"


def test_localhost_hostname_is_blocked():
    with pytest.raises(SSRFBlocked) as exc_info:
        validate_url("http://localhost/")
    assert exc_info.value.code == "private_target_blocked"


def test_private_class_a_range_is_blocked():
    with pytest.raises(SSRFBlocked) as exc_info:
        validate_url("http://10.0.0.5/")
    assert exc_info.value.code == "private_target_blocked"


def test_private_class_c_range_is_blocked():
    with pytest.raises(SSRFBlocked) as exc_info:
        validate_url("http://192.168.1.1/")
    assert exc_info.value.code == "private_target_blocked"


def test_cloud_metadata_endpoint_is_blocked():
    with pytest.raises(SSRFBlocked) as exc_info:
        validate_url("http://169.254.169.254/latest/meta-data/")
    assert exc_info.value.code == "private_target_blocked"


def test_link_local_ipv6_is_blocked():
    with pytest.raises(SSRFBlocked) as exc_info:
        validate_url("http://[fe80::1]/")
    assert exc_info.value.code == "private_target_blocked"


def test_ipv6_loopback_is_blocked():
    with pytest.raises(SSRFBlocked) as exc_info:
        validate_url("http://[::1]/")
    assert exc_info.value.code == "private_target_blocked"


def test_public_ip_literal_passes_validation():
    # 8.8.8.8 (a real public IP) is used only as a literal address --
    # getaddrinfo on a literal IP does not perform a network DNS query.
    result = validate_url("https://8.8.8.8/")
    assert result == "https://8.8.8.8/"


def test_disallowed_scheme_is_blocked():
    with pytest.raises(SSRFBlocked) as exc_info:
        validate_url("ftp://8.8.8.8/")
    assert exc_info.value.code == "scheme_not_allowed"


def test_disallowed_port_is_blocked():
    with pytest.raises(SSRFBlocked) as exc_info:
        validate_url("http://8.8.8.8:8080/")
    assert exc_info.value.code == "port_not_allowed"


def test_url_with_no_hostname_is_blocked():
    with pytest.raises(SSRFBlocked) as exc_info:
        validate_url("http:///just-a-path")
    assert exc_info.value.code == "invalid_url"


def test_credentials_in_url_do_not_bypass_host_validation():
    with pytest.raises(SSRFBlocked) as exc_info:
        validate_url("http://attacker:pw@127.0.0.1/")
    assert exc_info.value.code == "private_target_blocked"


# --- fetch() (D9.6 security suite) ------------------------------------------
#
# fetch() previously called an undefined `_validate_url` name on every
# invocation (only `validate_url` -- no underscore -- was ever defined),
# so it raised NameError on every call rather than ever reaching the
# network. These tests target that exact code path with private/literal
# IPs (no live network call happens, consistent with the rest of this
# file) -- they fail loudly with NameError if that regression returns,
# instead of the bug silently surviving because every test mocked fetch()
# away.


def test_fetch_blocks_private_target_without_raising_nameerror():
    with pytest.raises(SSRFBlocked) as exc_info:
        fetch("http://127.0.0.1/")
    assert exc_info.value.code == "private_target_blocked"


def test_fetch_blocks_metadata_endpoint_without_raising_nameerror():
    with pytest.raises(SSRFBlocked) as exc_info:
        fetch("http://169.254.169.254/latest/meta-data/")
    assert exc_info.value.code == "private_target_blocked"


def test_fetch_blocks_disallowed_scheme_without_raising_nameerror():
    with pytest.raises(SSRFBlocked) as exc_info:
        fetch("ftp://8.8.8.8/")
    assert exc_info.value.code == "scheme_not_allowed"
