"""Pure payload conversions for the existing webhook boundary."""

import re
import base64
import binascii
import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal, Mapping, Sequence
from urllib.parse import urlsplit


def language_base(code: str | None) -> str:
    """The short language Launchmind stores for an Odoo code; resolve_language_code reverses it."""
    base = (code or '').strip().replace('-', '_').split('_')[0].lower()
    return base or 'en'


def resolve_language_code(
    language: object,
    active_languages: Sequence[Mapping[str, str]],
    default_language: str | None = None,
) -> str | None:
    """Return an active res.lang code: exact, website default, then canonical/home-region codes.

    Odoo 18 exposes code, iso_code and url_code on res.lang. Only the
    canonical code is suitable for the ORM's lang context.
    """
    if not isinstance(language, str) or not language.strip():
        return None
    wanted = language.strip().replace('-', '_').lower()
    preferred = {'en': 'en_us'}.get(wanted, '%s_%s' % (wanted, wanted))
    matches = []
    for lang in active_languages:
        code = lang['code']
        normalized = code.lower()
        aliases = [
            (lang.get(key) or '').lower().replace('-', '_') for key in ('iso_code', 'url_code')
        ]
        if normalized == wanted or language_base(code) == wanted or wanted in aliases:
            matches.append(code)
    return min(
        matches,
        key=lambda code: (
            code.lower() != wanted,
            code != default_language,
            code.lower() != preferred,
            code,
        ),
        default=None,
    )


def parse_published_at(value: object) -> datetime | None:
    """Parse ISO publication time to Odoo's naive UTC datetime; ignore invalid input."""
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed
    except (ValueError, OverflowError):
        return None


def is_safe_cover_url(value: object) -> bool:
    """Allow only absolute HTTP(S) URLs safe inside an unquoted CSS url()."""
    if not isinstance(value, str) or not value or re.search(r'''[\s'"()\\]''', value):
        return False
    try:
        parsed = urlsplit(value)
        return parsed.scheme.lower() in ('http', 'https') and bool(parsed.hostname)
    except ValueError:
        return False


def extract_api_key(authorization: str, payload: object) -> str:
    """Bearer takes precedence; malformed body credentials never escape as objects."""
    if authorization.lower().startswith('bearer ') and authorization[7:].strip():
        return authorization[7:].strip()
    value = payload.get('api_key') if isinstance(payload, dict) else None
    return value.strip() if isinstance(value, str) else ''


# Launchmind ids are UUIDs; the bound keeps a check reply under the platform's 64 KiB cap.
MAX_ARTICLE_ID_LENGTH = 64


def _is_article_id(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip()) and len(value) <= MAX_ARTICLE_ID_LENGTH


@dataclass(frozen=True)
class UnpublishRequest:
    article_id: str


@dataclass(frozen=True)
class CheckRequest:
    article_ids: tuple[str, ...]


ImageMime = Literal['image/jpeg', 'image/png', 'image/gif', 'image/webp']
IMAGE_MIMES: tuple[ImageMime, ...] = ('image/jpeg', 'image/png', 'image/gif', 'image/webp')


@dataclass(frozen=True)
class Media:
    role: Literal['cover', 'inline']
    mime: ImageMime
    source_url: str
    alt: str
    sha256: str
    data: bytes


MAX_MEDIA_BYTES = 15 * 1024 * 1024


def sniff_image(data: bytes) -> ImageMime | None:
    """Only the bytes decide the type; the platform's sniffOdooImage decides the same.

    test/image_sniff_cases.json is the one measure for both runtimes.
    """
    if data.startswith(b'\xff\xd8\xff'):
        return 'image/jpeg'
    if data.startswith(b'\x89PNG\r\n\x1a\n'):
        return 'image/png'
    if data.startswith((b'GIF87a', b'GIF89a')):
        return 'image/gif'
    if data.startswith(b'RIFF') and data[8:12] == b'WEBP':
        return 'image/webp'
    return None


def parse_media(value: object) -> tuple[Media, ...]:
    """Invalid entries stay remote; bound work before decoding untrusted base64."""
    if not isinstance(value, list):
        return ()
    result = []
    total = 0
    for entry in value[:10]:
        if not isinstance(entry, dict):
            continue
        role, mime = entry.get('role'), entry.get('mime')
        source, alt = entry.get('source_url'), entry.get('alt', '')
        encoded, digest = entry.get('data'), entry.get('sha256')
        if (
            role not in ('cover', 'inline')
            or not isinstance(mime, str)
            or mime not in IMAGE_MIMES
            or not isinstance(source, str)
            or not source
            or not isinstance(alt, str)
            or not isinstance(encoded, str)
            or len(encoded) > 4 * ((MAX_MEDIA_BYTES - total + 2) // 3)
            or not isinstance(digest, str)
        ):
            continue
        try:
            data = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error):
            continue
        sniffed = sniff_image(data)
        if (
            len(data) + total > MAX_MEDIA_BYTES
            or sniffed is None
            or sniffed != mime
            or hashlib.sha256(data).hexdigest() != digest
        ):
            continue
        total += len(data)
        result.append(Media(role, sniffed, source, alt, digest, data))
    return tuple(result)


@dataclass(frozen=True)
class AuthorProfile:
    name: str
    role: str
    bio: str
    linkedin_url: str


def parse_author(author: str, key: object, profile: object) -> tuple[str, AuthorProfile]:
    """Keep external identity separate from the mutable display profile."""
    normalized = ' '.join(author.strip().lower().split())[:200]
    if not isinstance(key, str) or not re.fullmatch(
        r'(client_author:[0-9a-f-]{36}|name:.{1,200}|launchmind)', key
    ):
        key = 'name:' + normalized if normalized else 'launchmind'
    values = profile if isinstance(profile, dict) else {}

    def text(field: str, limit: int) -> str:
        value = values.get(field)
        return value.strip()[:limit] if isinstance(value, str) else ''

    linkedin = text('linkedin_url', 2048)
    try:
        url = urlsplit(linkedin)
        if url.scheme.lower() not in ('http', 'https') or not url.hostname:
            linkedin = ''
    except ValueError:
        linkedin = ''
    return key, AuthorProfile(
        text('name', 200) or author.strip()[:200] or 'Launchmind',
        text('role', 200),
        text('bio', 4000),
        linkedin,
    )


def parse_tags(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    labels: list[str] = []
    for label in value:
        if isinstance(label, str) and label.strip() and label.strip() not in labels:
            labels.append(label.strip())
            if len(labels) == 20:
                break
    return tuple(labels)


@dataclass(frozen=True)
class WebhookRequest:
    article_id: str
    title: str
    content: str
    excerpt: str
    author: str
    author_key: str
    author_profile: AuthorProfile
    tags: tuple[str, ...]
    seo_title: str
    meta_description: str
    meta_keywords: str
    language_code: str | None
    post_date: datetime | None
    # None preserves the existing cover, '' clears it, anything else is the
    # requested source; sync_media resolves it and decides what is safe.
    cover_source: str | None
    media: tuple[Media, ...]

    @classmethod
    def parse(
        cls,
        payload: object,
        active_languages: Sequence[Mapping[str, str]] = (),
        default_language: str | None = None,
    ) -> 'WebhookRequest | UnpublishRequest | CheckRequest':
        """Validate once before any writes; optional malformed values are ignored."""
        if not isinstance(payload, dict):
            raise ValueError('Body must be a JSON object')
        event = payload.get('event', 'article.published')
        if event == 'articles.check':
            ids = payload.get('article_ids')
            if (
                not isinstance(ids, list)
                or len(ids) > 500
                or not all(_is_article_id(value) for value in ids)
            ):
                raise ValueError('article_ids must be an array of at most 500 article ids')
            return CheckRequest(tuple(ids))
        if event not in ('article.published', 'article.unpublished'):
            raise ValueError('Unknown event')
        article = payload.get('article')
        if not isinstance(article, dict):
            raise ValueError('Missing or invalid article object')

        def required(key: str) -> str:
            value = article.get(key)
            if not isinstance(value, str) or not value.strip():
                raise ValueError('article must have id, title and content')
            return value

        def text(key: str) -> str:
            value = article.get(key)
            return value if isinstance(value, str) else ''

        if not _is_article_id(article.get('id')):
            raise ValueError(
                'article must have an id of at most %d characters' % MAX_ARTICLE_ID_LENGTH
            )
        if event == 'article.unpublished':
            return UnpublishRequest(required('id'))
        article_id, title, content = (required(key) for key in ('id', 'title', 'content'))
        tags = article.get('tags')
        keywords = ', '.join(
            tag.strip()
            for tag in (tags if isinstance(tags, list) else [])
            if isinstance(tag, str) and tag.strip()
        )[:255]
        author_key, author_profile = parse_author(
            text('author'), article.get('author_key'), article.get('author_profile')
        )
        cover_source = article.get('cover_image_url')
        return cls(
            article_id=article_id,
            title=title,
            content=content,
            excerpt=text('excerpt') or text('meta_description'),
            author=text('author').strip()[:200] or 'Launchmind',
            author_key=author_key,
            author_profile=author_profile,
            tags=parse_tags(tags),
            seo_title=(text('seo_title') or title)[:255],
            meta_description=text('meta_description'),
            meta_keywords=keywords,
            language_code=resolve_language_code(
                article.get('language'), active_languages, default_language
            ),
            post_date=parse_published_at(article.get('published_at')),
            cover_source=cover_source if isinstance(cover_source, str) else None,
            media=parse_media(payload.get('media')),
        )
