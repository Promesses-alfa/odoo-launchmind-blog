"""Pure lm-odoo-v2 signing, enrollment-response and runtime rules.

No Odoo import: test/test_signing.py runs these rules without an Odoo
installation, and the receiver and Connect action use the same functions.
The secret is a 64-character hex string used as UTF-8 text for the HMAC key,
never hex-decoded, so both runtimes derive the same key bytes.
"""

import hashlib
import hmac
import ipaddress
import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Callable
from urllib.parse import urlsplit

MODULE_VERSION = '18.0.1.6.0'
SUPPORTED_SERIES = '18.0'

SIGNATURE_HEADER = 'X-Launchmind-Signature'
KEY_ID_HEADER = 'X-Launchmind-Key-Id'
INSTALLATION_HEADER = 'X-Launchmind-Installation'
REQUEST_ID_HEADER = 'X-Launchmind-Request-Id'
TIMESTAMP_HEADER = 'X-Launchmind-Timestamp'
ACK_HEADER = 'X-Launchmind-Ack-Signature'
PROTOCOL_HEADERS = (
    SIGNATURE_HEADER,
    KEY_ID_HEADER,
    INSTALLATION_HEADER,
    REQUEST_ID_HEADER,
    TIMESTAMP_HEADER,
)

MAX_SKEW_SECONDS = 300
RECEIPT_TTL_SECONDS = 600
# Fifteen MiB of media is about 21 MiB of base64; the rest leaves room for
# article HTML. The cap is checked before any body is hashed.
MAX_SIGNED_BODY_BYTES = 32 * 1024 * 1024
MAX_REGISTER_RESPONSE_BYTES = 64 * 1024

REGISTER_EVENT = 'installation.register'
CONFIRM_EVENT = 'installation.confirm'

_UUID = re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}')
_SECRET = re.compile(r'[0-9a-f]{64}')
_TIMESTAMP = re.compile(r'0|[1-9][0-9]{0,15}')
# The largest integer both runtimes represent exactly (JavaScript safe integer).
MAX_TIMESTAMP = 2**53 - 1
_SIGNATURE = re.compile(r'v2=([0-9a-f]{64})')
_LOOPBACK_HOSTS = ('localhost', '127.0.0.1', '::1')


def is_uuid(value: object) -> bool:
    return isinstance(value, str) and _UUID.fullmatch(value) is not None


def is_secret(value: object) -> bool:
    return isinstance(value, str) and _SECRET.fullmatch(value) is not None


def runtime_supported(serie: object) -> bool:
    return serie == SUPPORTED_SERIES


def body_digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def canonical_request(
    installation_id: str, key_id: str, request_id: str, timestamp: int, raw: bytes
) -> bytes:
    return (
        'lm-odoo-v2\n%s\n%s\n%s\n%d\n%s'
        % (installation_id, key_id, request_id, timestamp, body_digest(raw))
    ).encode('utf-8')


def canonical_ack(request_id: str, raw_response: bytes) -> bytes:
    return ('lm-odoo-ack-v2\n%s\n%s' % (request_id, body_digest(raw_response))).encode('utf-8')


def sign(secret: str, message: bytes) -> str:
    return hmac.new(secret.encode('utf-8'), message, hashlib.sha256).hexdigest()


def request_headers(
    secret: str, installation_id: str, key_id: str, request_id: str, timestamp: int, raw: bytes
) -> dict[str, str]:
    signature = sign(secret, canonical_request(installation_id, key_id, request_id, timestamp, raw))
    return {
        SIGNATURE_HEADER: 'v2=' + signature,
        KEY_ID_HEADER: key_id,
        INSTALLATION_HEADER: installation_id,
        REQUEST_ID_HEADER: request_id,
        TIMESTAMP_HEADER: str(timestamp),
    }


def ack_signature(secret: str, request_id: str, raw_response: bytes) -> str:
    return 'v2=' + sign(secret, canonical_ack(request_id, raw_response))


@dataclass(frozen=True)
class SignedHeaders:
    signature: str
    key_id: str
    installation_id: str
    request_id: str
    timestamp: int


def parse_signed_headers(get: Callable[[str], str | None]) -> SignedHeaders | None:
    """Every protocol header must be present and canonical; anything else is no proof."""
    values = [get(name) for name in PROTOCOL_HEADERS]
    if not all(isinstance(value, str) for value in values):
        return None
    signature, key_id, installation_id, request_id, timestamp = values
    match = _SIGNATURE.fullmatch(signature or '')
    if (
        match is None
        or not is_uuid(key_id)
        or not is_uuid(installation_id)
        or not is_uuid(request_id)
        or _TIMESTAMP.fullmatch(timestamp or '') is None
        or int(str(timestamp)) > MAX_TIMESTAMP
    ):
        return None
    return SignedHeaders(
        match.group(1), str(key_id), str(installation_id), str(request_id), int(str(timestamp))
    )


def verify(secret: str, headers: SignedHeaders, raw: bytes) -> bool:
    expected = sign(
        secret,
        canonical_request(
            headers.installation_id, headers.key_id, headers.request_id, headers.timestamp, raw
        ),
    )
    return hmac.compare_digest(expected, headers.signature)


def fresh(timestamp: int, now: int) -> bool:
    return abs(now - timestamp) <= MAX_SKEW_SECONDS


def receipt_expiry(timestamp: int) -> int:
    """Anchored to the signed timestamp, so cleanup cannot reopen the replay window."""
    return timestamp + RECEIPT_TTL_SECONDS


def parse_confirm(payload: object) -> str:
    """Return the challenge of an exact confirmation body."""
    if (
        not isinstance(payload, dict)
        or set(payload) != {'event', 'challenge'}
        or payload['event'] != CONFIRM_EVENT
        or not is_uuid(payload['challenge'])
    ):
        raise ValueError('Invalid confirmation body')
    return payload['challenge']


def confirm_response(
    installation_id: str, key_id: str, challenge: str, runtime_version: str
) -> bytes:
    return json.dumps(
        {
            'success': True,
            'installation_id': installation_id,
            'key_id': key_id,
            'challenge': challenge,
            'runtime_series': SUPPORTED_SERIES,
            'runtime_version': runtime_version,
            'module_version': MODULE_VERSION,
        },
        separators=(',', ':'),
    ).encode('utf-8')


@dataclass(frozen=True)
class KeySlot:
    kid: str
    secret: str
    installation_id: str
    # Only a pending slot carries the platform's expiry (ISO 8601 with offset).
    expires_at: str | None = None


def dump_slot(slot: KeySlot) -> str:
    values = {'kid': slot.kid, 'secret': slot.secret, 'installation_id': slot.installation_id}
    if slot.expires_at is not None:
        values['expires_at'] = slot.expires_at
    return json.dumps(values, separators=(',', ':'), sort_keys=True)


def load_slot(text: str | None) -> KeySlot | None:
    """Empty is no slot; anything unreadable raises so callers fail closed."""
    if not text:
        return None
    value = json.loads(text)
    if (
        not isinstance(value, dict)
        or not set(value) <= {'kid', 'secret', 'installation_id', 'expires_at'}
        or not is_uuid(value.get('kid'))
        or not is_secret(value.get('secret'))
        or not is_uuid(value.get('installation_id'))
    ):
        raise ValueError('Corrupt key slot')
    expires_at = value.get('expires_at')
    if expires_at is not None:
        parse_expiry(expires_at)
    return KeySlot(value['kid'], value['secret'], value['installation_id'], expires_at)


def parse_expiry(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError('Invalid expiry')
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError('Expiry needs an offset')
    return parsed


@dataclass(frozen=True)
class Registration:
    subscription_id: str
    result: str
    kid: str
    # Only a pending grant carries key material.
    pending: KeySlot | None


def parse_registration(
    raw: bytes, installation_id: str, current_kid: str | None, now: datetime
) -> Registration:
    """Validate the entire Connect response before anything is persisted."""
    if len(raw) > MAX_REGISTER_RESPONSE_BYTES:
        raise ValueError('Response too large')
    value = json.loads(raw)
    if not isinstance(value, dict) or set(value) != {'success', 'subscription_id', 'enrollment'}:
        raise ValueError('Unexpected response shape')
    enrollment = value['enrollment']
    if value['success'] is not True or not is_uuid(value['subscription_id']):
        raise ValueError('Unexpected response shape')
    if not isinstance(enrollment, dict) or enrollment.get('installation_id') != installation_id:
        raise ValueError('Unexpected enrollment')
    kid = enrollment.get('kid')
    if not isinstance(kid, str) or not is_uuid(kid):
        raise ValueError('Unexpected enrollment')
    if enrollment.get('result') == 'confirmed':
        if set(enrollment) != {'result', 'kid', 'installation_id'} or kid != current_kid:
            raise ValueError('Unexpected enrollment')
        return Registration(value['subscription_id'], 'confirmed', kid, None)
    if (
        enrollment.get('result') != 'pending'
        or set(enrollment) != {'result', 'kid', 'secret', 'installation_id', 'expires_at'}
        or kid == current_kid
        or not is_secret(enrollment['secret'])
        or parse_expiry(enrollment['expires_at']) <= now
    ):
        raise ValueError('Unexpected enrollment')
    return Registration(
        value['subscription_id'],
        'pending',
        kid,
        KeySlot(kid, enrollment['secret'], installation_id, enrollment['expires_at']),
    )


def base_url_allowed(value: object, allow_loopback: bool) -> str | None:
    """Return scheme://host[:port] for a public HTTPS origin, else None.

    A loopback origin (http or https) is accepted only when the caller allows
    it; a private or reserved IP literal never is.
    """
    if not isinstance(value, str):
        return None
    try:
        parsed = urlsplit(value.strip())
        host = parsed.hostname
        parsed.port
    except ValueError:
        return None
    if (
        not host
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path not in ('', '/')
    ):
        return None
    origin = '%s://%s' % (parsed.scheme.lower(), parsed.netloc.lower())
    if host in _LOOPBACK_HOSTS:
        return origin if allow_loopback and parsed.scheme.lower() in ('http', 'https') else None
    if parsed.scheme.lower() != 'https':
        return None
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return origin if '.' in host else None
    return origin if address.is_global else None
