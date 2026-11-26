"""The one outbound HTTP boundary for telemetry, discovery and IndexNow.

HTTPS only, no redirects followed, no cookies, bounded time and bytes. A
failure is a safe code, never remote text. Tests replace ``_transport``
with a controlled receiver; the URL rules above it always run.
"""

import ipaddress
from dataclasses import dataclass
from typing import Callable
from urllib.parse import urlsplit

try:
    import requests
except ImportError:  # pragma: no cover - Odoo 18 ships requests
    requests = None  # type: ignore[assignment]


class OutboundError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class Reply:
    status: int
    headers: dict[str, str]
    body: bytes


def https_url_allowed(url: object) -> bool:
    """A public https URL without credentials; loopback and private literals never."""
    if not isinstance(url, str) or len(url) > 2048:
        return False
    try:
        parsed = urlsplit(url)
        host = parsed.hostname
        parsed.port
    except ValueError:
        return False
    if parsed.scheme != 'https' or not host or parsed.username or parsed.password:
        return False
    if host in ('localhost',) or host.endswith('.localhost'):
        return False
    try:
        return ipaddress.ip_address(host).is_global
    except ValueError:
        return '.' in host


def _requests_transport(
    method: str, url: str, data: bytes | None, headers: dict[str, str], timeout: float, limit: int
) -> Reply:
    if requests is None:
        raise OutboundError('requests_unavailable')
    try:
        response = requests.request(
            method,
            url,
            data=data,
            headers=headers,
            timeout=timeout,
            allow_redirects=False,
            stream=True,
        )
    except requests.exceptions.Timeout as exc:
        raise OutboundError('timeout') from exc
    except requests.exceptions.RequestException as exc:
        raise OutboundError('network_error') from exc
    try:
        chunks, size = [], 0
        for chunk in response.iter_content(8192):
            size += len(chunk)
            if size > limit:
                raise OutboundError('response_too_large')
            chunks.append(chunk)
    except requests.exceptions.RequestException as exc:
        raise OutboundError('network_error') from exc
    finally:
        response.close()
    return Reply(
        response.status_code,
        {key.lower(): value for key, value in response.headers.items()},
        b''.join(chunks),
    )


_transport: Callable[..., Reply] = _requests_transport


def send(
    method: str,
    url: str,
    *,
    data: bytes | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 5.0,
    limit: int = 64 * 1024,
) -> Reply:
    if not https_url_allowed(url):
        raise OutboundError('https_required')
    # A plain request has no cookie jar; a caller-supplied cookie is refused too.
    request_headers = {k: v for k, v in (headers or {}).items() if k.lower() != 'cookie'}
    return _transport(method, url, data, request_headers, timeout, limit)
