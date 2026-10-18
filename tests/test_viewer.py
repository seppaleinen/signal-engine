"""HTTP contract tests for the digest viewer.

Starts the real ThreadingHTTPServer from signal_engine.viewer against a temp
digest dir and exercises the full HTTP surface: GET, HEAD, and unsupported
methods. The HEAD invariant — zero body bytes with Content-Length matching
the would-be GET body — is asserted explicitly because the original do_HEAD
bug shipped a body on HEAD responses and survived the test stage.
"""

from __future__ import annotations

import http.client
import socket
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from signal_engine.viewer import _DigestHandler

# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def server():
    """Spin up _DigestHandler on an ephemeral port over a temp digest dir."""
    import tempfile

    tmp = Path(tempfile.mkdtemp(prefix="viewer-test-"))
    (tmp / "2026-10-16.md").write_text(
        "# 2026-10-16 - Test headline\n\n- item one\n- item two\n",
        encoding="utf-8",
    )
    (tmp / "2026-10-16.html").write_text(
        "<html><body>pre-rendered html</body></html>", encoding="utf-8"
    )

    _DigestHandler.digest_dir = tmp.resolve()
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _DigestHandler)
    port = srv.server_address[1]
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    try:
        yield {"host": "127.0.0.1", "port": port, "digest_dir": tmp}
    finally:
        srv.shutdown()
        srv.server_close()
        thread.join(timeout=2)


def _request(server: dict, method: str, path: str, *, timeout: float = 5.0):
    """Issue one HTTP request; return (status, headers-dict, body-bytes)."""
    conn = http.client.HTTPConnection(server["host"], server["port"], timeout=timeout)
    try:
        conn.request(method, path)
        resp = conn.getresponse()
        body = resp.read()
        headers = {k.lower(): v for k, v in resp.getheaders()}
        return resp.status, headers, body
    finally:
        conn.close()


def _raw_request(server: dict, method: str, path: str, *, timeout: float = 5.0) -> bytes:
    """Issue one HTTP request over a raw socket and return the unparsed wire bytes.

    http.client.HTTPResponse.read() returns b"" for every HEAD response by
    spec, so a library client cannot distinguish "server sent nothing" from
    "client declined to read". The do_HEAD bug shipped a body on HEAD and
    survived the test stage precisely because the test client never looked.
    Reading the raw socket is the only faithful way to assert the HEAD
    invariant, so this helper does that.
    """
    sock = socket.create_connection(
        (server["host"], server["port"]), timeout=timeout
    )
    try:
        sock.sendall(
            f"{method} {path} HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n".encode()
        )
        chunks: list[bytes] = []
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            chunks.append(chunk)
    finally:
        sock.close()
    return b"".join(chunks)


def _split_wire(raw: bytes) -> tuple[int, dict[str, bytes], bytes]:
    """Split raw HTTP response into (status, headers-dict, body-bytes)."""
    head, _, body = raw.partition(b"\r\n\r\n")
    lines = head.split(b"\r\n")
    status = int(lines[0].split(b" ", 2)[1])
    headers = {
        k.lower(): v
        for k, v in (
            line.split(b": ", 1) for line in lines[1:] if b": " in line
        )
    }
    return status, headers, body


# ---------------------------------------------------------------------------
# GET contract
# ---------------------------------------------------------------------------


def test_get_root_returns_200_with_index_html(server):
    status, headers, body = _request(server, "GET", "/")
    assert status == 200
    assert headers["content-type"].startswith("text/html")
    assert b"<title>Digests</title>" in body
    assert b"2026-10-16" in body  # the seeded digest appears in the index


def test_get_existing_date_directory_serves_digest(server):
    status, headers, body = _request(server, "GET", "/2026-10-16/")
    assert status == 200
    assert headers["content-type"].startswith("text/html")
    assert b"pre-rendered html" in body  # .html variant preferred over .md


def test_get_html_suffix_variant_serves_digest(server):
    status, headers, body = _request(server, "GET", "/2026-10-16.html")
    assert status == 200
    assert headers["content-type"].startswith("text/html")
    assert b"pre-rendered html" in body


def test_get_nonexistent_date_returns_404(server):
    status, headers, body = _request(server, "GET", "/2099-01-01/")
    assert status == 404
    assert b"Not found" in body


def test_get_path_traversal_is_rejected(server):
    status, headers, body = _request(server, "GET", "/../../etc/passwd")
    assert status in (400, 404)
    assert b"root:" not in body  # no file leak
    assert b"Bad request" in body or b"Not found" in body


def test_get_bad_date_format_returns_400(server):
    status, headers, body = _request(server, "GET", "/bad-date/")
    assert status == 400
    assert b"Bad request" in body


# ---------------------------------------------------------------------------
# HEAD contract — the invariant this contract exists to protect
# ---------------------------------------------------------------------------


def _expected_body_for(server: dict, path: str) -> bytes:
    """Fetch the GET body for a path so HEAD can be compared against it."""
    _, _, body = _request(server, "GET", path)
    return body


def _test_head_on_wire(server, path):
    """Assert HEAD on *path* has zero wire body and Content-Length matching GET."""
    expected = _expected_body_for(server, path)
    raw = _raw_request(server, "HEAD", path)
    status, headers, wire_body = _split_wire(raw)

    assert status == 200
    assert headers[b"content-length"]
    assert int(headers[b"content-length"]) == len(expected)
    assert wire_body == b""  # the do_HEAD bug shipped a body here


def test_head_root_has_empty_body_and_matching_content_length(server):
    _test_head_on_wire(server, "/")


def test_head_date_directory_has_empty_body_and_matching_content_length(server):
    _test_head_on_wire(server, "/2026-10-16/")


def test_head_html_suffix_has_empty_body_and_matching_content_length(server):
    _test_head_on_wire(server, "/2026-10-16.html")


def test_head_nonexistent_date_returns_404_with_empty_body(server):
    raw = _raw_request(server, "HEAD", "/2099-01-01/")
    status, headers, wire_body = _split_wire(raw)
    assert status == 404
    assert wire_body == b""
    assert b"content-length" in headers


# ---------------------------------------------------------------------------
# unsupported methods
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("method", ["POST", "OPTIONS", "PUT", "DELETE"])
def test_unsupported_methods_are_rejected(server, method):
    status, headers, body = _request(server, method, "/")
    # BaseHTTPRequestHandler returns 501 for methods it does not override.
    assert status in (404, 405, 501)