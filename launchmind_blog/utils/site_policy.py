"""Pure discovery policy: robots rules, rendered restrictions, IndexNow semantics.

Every decision that could promote a URL lives here, so the background
refresh, /llms.txt and the IndexNow dispatcher share one authority. Unknown
or unsupported evidence is never read as permission.
"""

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from html.parser import HTMLParser
from typing import Mapping, Sequence
from urllib.parse import urlsplit

from .signing import MODULE_VERSION, base_url_allowed, confirm_response

INDEXNOW_ENDPOINT = 'https://api.indexnow.org/indexnow'
INDEXNOW_BATCH = 100
INDEXNOW_KEY = re.compile(r'[A-Za-z0-9-]{32,128}')
MAX_ATTEMPTS = 12
LLMS_LIMIT = 200
MAX_PAGE_BYTES = 2 * 1024 * 1024
MAX_ROBOTS_BYTES = 512 * 1024
PERMIT_MAX_SECONDS = 90

# Search engines that consume IndexNow; their own robots groups are honoured
# alongside the wildcard group, never instead of it.
INDEXNOW_AGENTS = ('bingbot', 'yandex', 'yandexbot', 'seznambot', 'naver', 'yeti', 'yep')
_KNOWN_FIELDS = ('user-agent', 'allow', 'disallow', 'sitemap', 'crawl-delay', 'host')


def production_origin(value: object) -> str | None:
    """An exact https origin as typed; no path, credentials, loopback or private host."""
    origin = base_url_allowed(value, allow_loopback=False)
    return origin if origin is not None and origin == value else None


def is_indexnow_key(value: object) -> bool:
    return isinstance(value, str) and INDEXNOW_KEY.fullmatch(value) is not None


# ---------------------------------------------------------------------------
# robots.txt
# ---------------------------------------------------------------------------


@dataclass
class RobotsGroup:
    agents: list[str] = field(default_factory=list)
    rules: list[tuple[bool, str]] = field(default_factory=list)
    unsupported: bool = False


def parse_robots(text: str) -> list[RobotsGroup]:
    groups: list[RobotsGroup] = []
    current: RobotsGroup | None = None
    collecting_agents = False
    for raw_line in text.splitlines():
        line = raw_line.split('#', 1)[0].strip()
        if not line:
            continue
        if ':' not in line:
            if current is not None:
                current.unsupported = True
            continue
        name, value = (part.strip() for part in line.split(':', 1))
        name = name.lower()
        if name == 'user-agent':
            if current is None or not collecting_agents:
                current = RobotsGroup()
                groups.append(current)
            current.agents.append(value.lower())
            collecting_agents = True
            continue
        collecting_agents = False
        if current is None or name in ('sitemap', 'host', 'crawl-delay'):
            continue
        if name in ('allow', 'disallow'):
            current.rules.append((name == 'allow', value))
        elif name not in _KNOWN_FIELDS:
            current.unsupported = True
    return groups


def _rule_matches(pattern: str, path: str) -> bool:
    anchored = pattern.endswith('$')
    body = pattern[:-1] if anchored else pattern
    regex = '.*'.join(re.escape(part) for part in body.split('*'))
    return re.match(regex + ('$' if anchored else ''), path) is not None


def _group_allows(group: RobotsGroup, path: str) -> bool:
    best: tuple[int, bool] | None = None
    for allow, pattern in group.rules:
        if not pattern:
            continue
        if _rule_matches(pattern, path):
            candidate = (len(pattern), allow)
            # Longest match wins; on a tie Allow wins (RFC 9309).
            if best is None or candidate[0] > best[0] or (candidate[0] == best[0] and allow):
                best = candidate
    return best is None or best[1]


def _relevant_groups(groups: Sequence[RobotsGroup]) -> list[RobotsGroup]:
    return [
        group
        for group in groups
        if any(agent == '*' or agent in INDEXNOW_AGENTS for agent in group.agents)
    ]


def robots_site_hold(groups: Sequence[RobotsGroup]) -> str | None:
    relevant = _relevant_groups(groups)
    if any(group.unsupported for group in relevant):
        return 'robots_unsupported'
    if any(not _group_allows(group, '/') for group in relevant):
        return 'robots_restrictive'
    return None


def robots_allows(groups: Sequence[RobotsGroup], url: str) -> bool:
    parts = urlsplit(url)
    path = (parts.path or '/') + ('?' + parts.query if parts.query else '')
    return all(_group_allows(group, path) for group in _relevant_groups(groups))


# ---------------------------------------------------------------------------
# Rendered page evidence
# ---------------------------------------------------------------------------


class _PageFacts(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.canonicals: list[str] = []
        self.noindex = False
        self.login_form = False

    def handle_starttag(self, tag, attrs):
        values = {name.lower(): (value or '') for name, value in attrs}
        if tag == 'link' and 'canonical' in values.get('rel', '').lower().split():
            self.canonicals.append(values.get('href', ''))
        elif tag == 'meta' and values.get('name', '').lower() in (
            'robots',
            'googlebot',
            'bingbot',
        ):
            if _noindex(values.get('content', '')):
                self.noindex = True
        elif tag == 'form' and '/web/login' in values.get('action', ''):
            self.login_form = True


def _noindex(value: str) -> bool:
    tokens = {token.strip().lower() for token in re.split(r'[,\s]+', value) if token.strip()}
    return bool(tokens & {'noindex', 'none'})


def x_robots_noindex(header: str | None) -> bool:
    if not header:
        return False
    # "bingbot: noindex" or "noindex, nofollow"; a scoped directive counts too.
    return any(_noindex(part.split(':', 1)[-1]) for part in header.split(','))


def rendered_restriction(
    status: int, headers: Mapping[str, str], body: bytes, expected_url: str
) -> str | None:
    """None when this anonymous response proves the URL is public and canonical."""
    if 300 <= status < 400:
        return 'redirected'
    if status != 200:
        return 'http_%d' % status
    if 'text/html' not in headers.get('content-type', '').lower():
        return 'not_html'
    if x_robots_noindex(headers.get('x-robots-tag')):
        return 'x_robots_noindex'
    facts = _PageFacts()
    try:
        facts.feed(body.decode('utf-8', errors='replace'))
    except Exception:
        return 'unparseable_page'
    if facts.noindex:
        return 'meta_noindex'
    if facts.login_form:
        return 'login_page'
    if not facts.canonicals:
        return 'canonical_missing'
    # HTMLParser already decoded character references in attribute values.
    if len(set(facts.canonicals)) != 1 or facts.canonicals[0] != expected_url:
        return 'canonical_mismatch'
    return None


def fingerprint(values: Mapping[str, object]) -> str:
    """Content identity; callers exclude view counters and connector timestamps."""
    encoded = json.dumps(values, sort_keys=True, separators=(',', ':'), default=str)
    return hashlib.sha256(encoded.encode('utf-8')).hexdigest()


# ---------------------------------------------------------------------------
# IndexNow
# ---------------------------------------------------------------------------


def indexnow_body(origin: str, key: str, urls: Sequence[str]) -> bytes:
    return json.dumps(
        {
            'host': urlsplit(origin).hostname,
            'key': key,
            'keyLocation': '%s/%s.txt' % (origin, key),
            'urlList': list(urls),
        },
        separators=(',', ':'),
    ).encode('utf-8')


def classify_indexnow(status: int) -> tuple[str, str | None]:
    """('accepted' | 'blocked' | 'retry', safe code). 200/202 mean received, not indexed."""
    if status == 200:
        return 'accepted', None
    if status == 202:
        return 'accepted', 'key_pending'
    if status in (400, 403, 422):
        return 'blocked', 'indexnow_%d' % status
    if status == 429 or 500 <= status < 600:
        return 'retry', 'indexnow_%d' % status
    if 300 <= status < 400:
        return 'retry', 'unexpected_redirect'
    return 'retry', 'unexpected_%d' % status


def safe_error(body: bytes) -> str | None:
    """Only a bounded protocol code may enter the local diagnostic ledger."""
    try:
        code = json.loads(body).get('error')
    except (ValueError, AttributeError):
        return None
    return code if isinstance(code, str) and re.fullmatch(r'[a-z0-9_]{1,48}', code) else None


def backoff(attempts: int) -> timedelta:
    return timedelta(seconds=min(60 * 2 ** max(attempts - 1, 0), 86400))


def proof_body(
    installation_id: str, key_id: str, challenge: str, runtime_version: str, indexnow_key: str
) -> bytes:
    # The signed confirmation owns the identity/runtime wire fields.
    value = json.loads(confirm_response(installation_id, key_id, challenge, runtime_version))
    value['indexnow_key'] = indexnow_key
    return json.dumps(value, separators=(',', ':')).encode('utf-8')


def permit_request_body(origin: str, indexnow_key: str) -> bytes:
    return json.dumps(
        {
            'event': 'installation.indexnow.verify',
            'production': True,
            'origin': origin,
            'indexnow_key': indexnow_key,
        },
        separators=(',', ':'),
    ).encode('utf-8')


def parse_permit(
    raw: bytes,
    origin: str,
    installation_id: str,
    key_id: str,
    indexnow_key: str,
    now: datetime,
) -> datetime:
    """Validate the platform's 60-second permit for exactly this binding; raise otherwise."""
    value = json.loads(raw)
    if not isinstance(value, dict) or set(value) != {'success', 'permit'}:
        raise ValueError('Unexpected permit')
    permit = value['permit']
    if (
        value['success'] is not True
        or not isinstance(permit, dict)
        or set(permit) != {'origin', 'installation_id', 'key_id', 'indexnow_key', 'expires_at'}
        or permit['origin'] != origin
        or permit['installation_id'] != installation_id
        or permit['key_id'] != key_id
        or permit['indexnow_key'] != indexnow_key
        or not isinstance(permit['expires_at'], str)
    ):
        raise ValueError('Unexpected permit')
    expires = datetime.fromisoformat(permit['expires_at'].replace('Z', '+00:00'))
    if expires.tzinfo is None or not now < expires <= now + timedelta(seconds=PERMIT_MAX_SECONDS):
        raise ValueError('Permit not current')
    return expires


# ---------------------------------------------------------------------------
# /llms.txt
# ---------------------------------------------------------------------------


def _text(value: str, limit: int) -> str:
    collapsed = ' '.join((value or '').split())[:limit]
    return re.sub(r'([\\`*_\[\]()<>#!|])', r'\\\1', collapsed)


def llms_text(site_name: str, entries: Sequence[tuple[str, str]]) -> str:
    lines = [
        '# %s' % (_text(site_name, 200) or 'Articles'),
        '',
        '> Articles published through Launchmind on this site and verified as public '
        'by an anonymous check. At most %d URLs, newest first; this is not a complete '
        'index of the website.' % LLMS_LIMIT,
        '',
        '## Articles',
        '',
    ]
    for title, url in entries[:LLMS_LIMIT]:
        lines.append('- [%s](<%s>)' % (_text(title, 300) or url, url.replace('>', '%3E')))
    return '\n'.join(lines) + '\n'
