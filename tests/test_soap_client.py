"""Tests for the digest handshake of the SOAP client.

The master answers a request without credentials with HTTP 401 and a digest
challenge. The client keeps that challenge, so only the first request and one
after the master has dropped the nonce need a second round trip.
"""
from __future__ import annotations

import io
import urllib.error
from email.message import Message

import pytest

from custom_components.innoxel import soap_client
from custom_components.innoxel.soap_client import (
    InnoxelAuthError,
    _DigestAuth,
    _sync_soap_call,
)

URL = "http://192.0.2.10:5001/control"
CHALLENGE = 'Digest realm="noxnet", nonce="abc123", qop="auth", algorithm=MD5'


class _Answer:
    """Minimal stand-in for the response object of urllib."""

    status = 200

    def __init__(self, body: str = "<ok/>") -> None:
        self._body = body.encode()

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> _Answer:
        return self

    def __exit__(self, *exc: object) -> None:
        return None


def _unauthorized(challenge: str | None = CHALLENGE) -> urllib.error.HTTPError:
    headers = Message()
    if challenge:
        headers["WWW-Authenticate"] = challenge
    return urllib.error.HTTPError(URL, 401, "Unauthorized", headers, io.BytesIO(b""))


class _Master:
    """Plays back a list of answers and records the requests it was sent."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, answers: list) -> None:
        self.answers = list(answers)
        self.authorizations: list[str | None] = []
        monkeypatch.setattr(soap_client._OPENER, "open", self._open)

    def _open(self, req, timeout=None):
        self.authorizations.append(req.get_header("Authorization"))
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


def test_header_matches_the_rfc_2617_example(monkeypatch: pytest.MonkeyPatch) -> None:
    """The worked example of RFC 2617, section 3.5."""
    monkeypatch.setattr(soap_client.os, "urandom", lambda n: bytes.fromhex("0a4f113b"))
    auth = _DigestAuth("Mufasa", "Circle Of Life")
    assert auth.header("GET", "/dir/index.html") is None
    assert auth.update(
        'Digest realm="testrealm@host.com", qop="auth,auth-int", '
        'nonce="dcd98b7102dd2f0e8b11d0f600bfb0c093", '
        'opaque="5ccc069c403ebaf9f0171e9517f40e41"'
    )
    header = auth.header("GET", "/dir/index.html")
    assert header is not None
    assert 'response="6629fae49393a05397450978507c4ef1"' in header
    assert "nc=00000001" in header
    assert 'opaque="5ccc069c403ebaf9f0171e9517f40e41"' in header


def test_header_without_qop() -> None:
    """A challenge without qop is answered the RFC 2069 way, without nc and cnonce."""
    auth = _DigestAuth("Mufasa", "Circle Of Life")
    assert auth.update('Digest realm="testrealm@host.com", nonce="dcd98b7102dd2f0e8b11d0f600bfb0c093"')
    header = auth.header("GET", "/dir/index.html")
    assert header is not None
    assert 'response="670fd8c2df070c60b045671b8b24ff02"' in header
    assert "nc=" not in header and "cnonce" not in header


@pytest.mark.parametrize(
    "challenge",
    [None, "", 'Basic realm="noxnet"', 'Digest realm="noxnet"', 'Digest nonce="x", algorithm=FOO'],
)
def test_unusable_challenges_are_refused(challenge: str | None) -> None:
    auth = _DigestAuth("ha", "secret")
    assert auth.update(challenge) is False
    assert auth.header("POST", "/control") is None


def test_first_call_does_the_handshake_then_the_challenge_is_kept(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    master = _Master(monkeypatch, [_unauthorized(), _Answer("<one/>"), _Answer("<two/>"), _Answer("<three/>")])
    auth = _DigestAuth("ha", "secret")

    assert _sync_soap_call(URL, auth, "getState", "") == "<one/>"
    assert _sync_soap_call(URL, auth, "getState", "") == "<two/>"
    assert _sync_soap_call(URL, auth, "getState", "") == "<three/>"

    # Four requests for three calls: only the very first went out twice.
    assert len(master.authorizations) == 4
    assert master.authorizations[0] is None
    counts = [a.split("nc=")[1][:8] for a in master.authorizations[1:]]
    assert counts == ["00000001", "00000002", "00000003"]
    assert all('uri="/control"' in a and 'nonce="abc123"' in a for a in master.authorizations[1:])


def test_a_dropped_nonce_is_renewed_with_one_extra_request(monkeypatch: pytest.MonkeyPatch) -> None:
    auth = _DigestAuth("ha", "secret")
    assert auth.update(CHALLENGE)
    fresh = 'Digest realm="noxnet", nonce="new456", qop="auth"'
    master = _Master(monkeypatch, [_unauthorized(fresh), _Answer("<ok/>")])

    assert _sync_soap_call(URL, auth, "getState", "") == "<ok/>"

    assert 'nonce="abc123"' in master.authorizations[0]
    assert 'nonce="new456"' in master.authorizations[1]
    # The count starts again with the new nonce.
    assert "nc=00000001" in master.authorizations[1]


def test_wrong_credentials_raise_after_two_requests(monkeypatch: pytest.MonkeyPatch) -> None:
    master = _Master(monkeypatch, [_unauthorized(), _unauthorized()])
    with pytest.raises(InnoxelAuthError):
        _sync_soap_call(URL, _DigestAuth("ha", "wrong"), "getState", "")
    assert len(master.authorizations) == 2


def test_a_401_without_digest_challenge_raises_at_once(monkeypatch: pytest.MonkeyPatch) -> None:
    master = _Master(monkeypatch, [_unauthorized('Basic realm="noxnet"')])
    with pytest.raises(InnoxelAuthError):
        _sync_soap_call(URL, _DigestAuth("ha", "secret"), "getState", "")
    assert len(master.authorizations) == 1


def test_other_http_errors_are_passed_on(monkeypatch: pytest.MonkeyPatch) -> None:
    error = urllib.error.HTTPError(URL, 500, "Server Error", Message(), io.BytesIO(b"fault"))
    _Master(monkeypatch, [error])
    auth = _DigestAuth("ha", "secret")
    assert auth.update(CHALLENGE)
    with pytest.raises(urllib.error.HTTPError) as caught:
        _sync_soap_call(URL, auth, "getState", "")
    assert caught.value.code == 500
