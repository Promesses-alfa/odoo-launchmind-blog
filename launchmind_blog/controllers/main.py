# -*- coding: utf-8 -*-
"""
Launchmind Blog — Webhook Controller

Article receiver (with a separate lightweight health endpoint):

    POST /launchmind-blog/webhook
    Authorization: Bearer <LAUNCHMIND_API_KEY>
    Content-Type: application/json

Receives a single article payload from launchmind.io and creates (or
updates) a corresponding ``blog.post`` record in Odoo's native
``website_blog`` module. Before the first signed enrollment the bearer
token is verified against the API key the merchant configured in
Settings > Website > Launchmind Blog. Once Connect has stored a signing key
(see utils/signing.py for the lm-odoo-v2 wire format), only HMAC-signed,
replay-protected requests are accepted, and any request carrying a
signature header is judged on its signature alone.

Idempotency
-----------
Each Launchmind article carries a unique ``id``. We store that id in
``blog.post.launchmind_article_id`` so a re-delivered webhook simply
updates the existing post instead of creating a duplicate. Legacy keyword markers are adopted
once and backfilled into this field. Retry policy belongs to the sender.
"""

import json
import logging
import time
from urllib.parse import urljoin
from typing import Any

from odoo import http, fields, release
from odoo.http import request, Response

from ..utils.enrollment import (
    PARAM_API_KEY,
    PARAM_CURRENT,
    PARAM_PENDING,
    fresh_param,
    lock,
    read_state,
    write_slot,
)
from ..utils.signing import (
    ACK_HEADER,
    CONFIRM_EVENT,
    MAX_SIGNED_BODY_BYTES,
    PROTOCOL_HEADERS,
    KeySlot,
    ack_signature,
    confirm_response,
    fresh,
    parse_confirm,
    parse_expiry,
    parse_signed_headers,
    runtime_supported,
    verify,
)

from ..utils.html_sanitize import excerpt_as_text, sanitize_article_html
from ..utils.media import sync_media
from ..utils.destination import DestinationNotConfigured, resolve_destination
from ..utils.webhook_values import (
    CheckRequest,
    UnpublishRequest,
    WebhookRequest,
    extract_api_key,
)

_logger = logging.getLogger(__name__)


def _json_response(payload, status=200):
    """Helper: serialize a dict to a JSON HTTP response."""
    return Response(
        json.dumps(payload),
        status=status,
        headers={'Content-Type': 'application/json; charset=utf-8'},
    )


class LaunchmindBlogWebhookController(http.Controller):

    @http.route(
        '/launchmind-blog/webhook',
        type='http',
        auth='public',
        methods=['POST'],
        csrf=False,
        save_session=False,
    )
    def webhook(self, **kwargs):
        """Receive a published article from launchmind.io and create a blog.post."""
        httprequest = request.httprequest
        # Any protocol header, even the acknowledgement header alone, selects the
        # signed path; a bearer is never read there.
        if any(name in httprequest.headers for name in PROTOCOL_HEADERS + (ACK_HEADER,)):
            return _signed_webhook(request.env, httprequest)

        # ------------------------------------------------------------------
        # 1. Auth (legacy bearer, only before any signed enrollment)
        # ------------------------------------------------------------------
        lock(request.env)
        if read_state(request.env).ratchet:
            return _json_response({'error': 'signature_required'}, status=401)
        configured_key = fresh_param(request.env, PARAM_API_KEY).strip()

        if not configured_key:
            _logger.warning('[Launchmind] Webhook called but no API key is configured')
            return _json_response(
                {
                    'error': 'Launchmind module is not connected on this Odoo. Configure it under Settings > Website > Launchmind Blog.'
                },
                status=503,
            )

        try:
            payload = json.loads(request.httprequest.get_data(as_text=True) or '{}')
        except ValueError:
            payload = None

        provided_key = extract_api_key(
            request.httprequest.headers.get('Authorization', '') or '', payload
        )
        if not provided_key or not _safe_eq(provided_key, configured_key):
            return _json_response({'error': 'Unauthorized'}, status=401)
        if payload is None:
            return _json_response({'error': 'Invalid JSON body'}, status=400)

        try:
            article = WebhookRequest.parse(
                payload,
                request.env['res.lang']
                .sudo()
                .search_read([('active', '=', True)], ['code', 'iso_code', 'url_code']),
                request.env['website'].get_current_website().default_lang_id.code,
            )
        except ValueError as exc:
            return _json_response({'error': str(exc)}, status=400)

        try:
            # Returning an error response still commits the HTTP transaction.
            # Keep failed article work atomic and leave the cursor usable.
            with request.env.cr.savepoint():
                result = apply_webhook(request.env, article)
        except DestinationNotConfigured as exc:
            return _json_response(
                {'error': 'destination_not_configured', 'message': str(exc)}, status=409
            )
        except Exception as exc:  # pragma: no cover - defensive ORM boundary
            _logger.exception('[Launchmind] Failed to apply webhook')
            return _json_response({'error': 'Failed to save post: %s' % str(exc)}, status=500)
        return _json_response(result)

    @http.route(
        '/launchmind-blog/health',
        type='http',
        auth='public',
        methods=['GET'],
        csrf=False,
        save_session=False,
    )
    def health(self, **kwargs):
        """Lightweight health endpoint Launchmind can ping to verify the
        webhook receiver is reachable. Does NOT expose the API key."""
        ICP = request.env['ir.config_parameter'].sudo()
        connected = (ICP.get_param('launchmind_blog.connected') or '').lower() == 'true'
        last_received = ICP.get_param('launchmind_blog.last_received_at') or None
        return _json_response(
            {
                'ok': True,
                'connected': connected,
                'last_received_at': last_received,
            },
            status=200,
        )


def _signed_webhook(env: Any, httprequest: Any) -> Response:
    """HMAC-only receiver. No failure here ever consults a bearer credential."""
    length = httprequest.content_length
    if length is not None and length > MAX_SIGNED_BODY_BYTES:
        return _json_response({'error': 'payload_too_large'}, status=413)
    raw = httprequest.get_data()
    if len(raw) > MAX_SIGNED_BODY_BYTES:
        return _json_response({'error': 'payload_too_large'}, status=413)
    headers = parse_signed_headers(httprequest.headers.get)
    if headers is None:
        return _json_response({'error': 'invalid_signature'}, status=401)
    lock(env)
    state = read_state(env)
    if state.corrupt:
        return _json_response({'error': 'enrollment_unavailable'}, status=503)
    if not state.bound or headers.installation_id != state.database_uuid:
        return _json_response({'error': 'installation_mismatch'}, status=401)
    match = state.slot(headers.key_id)
    if match is None or not verify(match[1].secret, headers, raw):
        return _json_response({'error': 'invalid_signature'}, status=401)
    role, slot = match
    if not fresh(headers.timestamp, int(time.time())):
        return _json_response({'error': 'stale_timestamp'}, status=401)
    if not state.connected:
        return _json_response({'error': 'not_connected'}, status=503)
    # The receipt commits with the response, including a failed apply, so a
    # signed request is never applied twice; the sender retries with a new id.
    if (
        not env['launchmind.blog.receipt']
        .sudo()
        ._admit(slot.kid, headers.request_id, headers.timestamp)
    ):
        return _json_response({'error': 'replayed'}, status=409)
    try:
        payload = json.loads(raw)
    except ValueError:
        return _json_response({'error': 'Invalid JSON body'}, status=400)
    if isinstance(payload, dict) and payload.get('event') == CONFIRM_EVENT:
        return _confirm(env, role, slot, headers.request_id, payload)
    if role == 'pending':
        return _json_response({'error': 'confirmation_required'}, status=403)
    if state.pending is not None:
        return _json_response({'error': 'enrollment_pending'}, status=409)
    if isinstance(payload, dict) and 'api_key' in payload:
        return _json_response({'error': 'api_key_not_allowed'}, status=400)
    try:
        article = WebhookRequest.parse(
            payload,
            env['res.lang']
            .sudo()
            .search_read([('active', '=', True)], ['code', 'iso_code', 'url_code']),
            env['website'].get_current_website().default_lang_id.code,
        )
    except ValueError as exc:
        return _json_response({'error': str(exc)}, status=400)
    try:
        with env.cr.savepoint():
            result = apply_webhook(env, article)
    except DestinationNotConfigured as exc:
        return _json_response(
            {'error': 'destination_not_configured', 'message': str(exc)}, status=409
        )
    except Exception:
        _logger.exception('[Launchmind] Signed webhook rolled back')
        return _json_response({'error': 'save_failed'}, status=500)
    return _json_response(result)


def _confirm(env: Any, role: str, slot: KeySlot, request_id: str, payload: Any) -> Response:
    """Promote a pending key, or re-acknowledge the current one after a lost ACK."""
    try:
        challenge = parse_confirm(payload)
    except ValueError:
        return _json_response({'error': 'invalid_confirmation'}, status=400)
    if not runtime_supported(release.serie):
        return _json_response({'error': 'incompatible_runtime'}, status=409)
    if role == 'pending':
        if slot.expires_at is None or parse_expiry(slot.expires_at).timestamp() <= time.time():
            return _json_response({'error': 'enrollment_expired'}, status=409)
        write_slot(env, PARAM_CURRENT, KeySlot(slot.kid, slot.secret, slot.installation_id))
        write_slot(env, PARAM_PENDING, None)
    body = confirm_response(slot.installation_id, slot.kid, challenge, release.version)
    return Response(
        body,
        status=200,
        headers={
            'Content-Type': 'application/json',
            ACK_HEADER: ack_signature(slot.secret, request_id, body),
        },
    )


def _owned_post(env: Any, article_id: str) -> Any:
    """Resolve both dedicated and legacy identities, including archived posts."""
    posts = env['blog.post'].sudo().with_context(active_test=False)
    existing = posts.search([('launchmind_article_id', '=', article_id)], limit=1)
    if existing:
        return existing
    blog = env['blog.blog'].sudo().search([('name', '=', 'Launchmind Blog')], limit=1)
    if not blog:
        return posts.browse()
    # Match a complete legacy marker, not a substring belonging to another id.
    candidates = posts.search(
        [
            ('blog_id', '=', blog.id),
            ('launchmind_article_id', '=', False),
            ('website_meta_keywords', 'ilike', 'lm:%s' % article_id),
        ]
    )
    for post in candidates:
        if 'lm:%s' % article_id in [
            keyword.strip() for keyword in (post.website_meta_keywords or '').split(',')
        ]:
            return post
    return posts.browse()


def apply_webhook(
    env: Any, article: WebhookRequest | UnpublishRequest | CheckRequest
) -> dict[str, Any]:
    """Apply an already parsed request using Odoo's native ORM and sanitizer."""
    if isinstance(article, CheckRequest):
        stale = []
        for article_id in article.article_ids:
            post = _owned_post(env, article_id)
            if not post or not post.active or not post.is_published:
                stale.append(article_id)
        return {'success': True, 'stale': stale}
    existing = _owned_post(env, article.article_id)
    if isinstance(article, UnpublishRequest):
        if existing:
            existing.write(
                {
                    'launchmind_article_id': article.article_id,
                    'is_published': False,
                }
            )
        return {
            'success': True,
            'action': 'unpublished' if existing else 'absent',
            'post_id': existing.id if existing else None,
            'article_id': article.article_id,
        }
    blog = resolve_destination(env)
    BlogPost = env['blog.post'].sudo().with_context(active_test=False)
    if article.language_code:
        BlogPost = BlogPost.with_context(lang=article.language_code)
        if existing:
            existing = existing.with_context(lang=article.language_code)

    partners = env['res.partner'].sudo().with_context(active_test=False)
    author = partners.search([('launchmind_author_key', '=', article.author_key)], limit=1)
    profile = article.author_profile
    author_values = {
        'name': profile.name,
        'function': profile.role,
        'website': profile.linkedin_url,
        'comment': profile.bio,
    }
    if author:
        author.write(author_values)
    else:
        author = partners.create(
            dict(author_values, company_type='person', launchmind_author_key=article.author_key)
        )
    tags = env['blog.tag'].sudo()
    if article.language_code:
        tags = tags.with_context(lang=article.language_code)
    tag_ids = []
    for label in article.tags:
        tag = tags.search([('name', '=', label)], limit=1)
        if not tag:
            tag = tags.create({'name': label})
        tag_ids.append(tag.id)
    post_vals = {
        'launchmind_article_id': article.article_id,
        'name': article.title,
        'subtitle': excerpt_as_text(article.excerpt)[:255],
        'content': sanitize_article_html(article.content),
        'tag_ids': [(6, 0, tag_ids)],
        'author_id': author.id,
        'is_published': True,
        'active': True,
        'website_meta_title': article.seo_title,
        'website_meta_description': excerpt_as_text(article.meta_description)[:255],
        'website_meta_keywords': article.meta_keywords,
    }
    if article.post_date is not None:
        post_vals['post_date'] = article.post_date
    if existing:
        action = 'restored' if not existing.active or not existing.is_published else 'updated'
        existing.write(post_vals)
        post = existing
    else:
        post_vals['blog_id'] = blog.id
        post, action = BlogPost.create(post_vals), 'created'
    media_deferred = False
    try:
        # The text write is flushed when the savepoint opens, so a failure
        # rolls back only the image work; the next delivery retries it.
        with env.cr.savepoint():
            sync_media(env, post, article)
    except Exception:
        _logger.exception('[Launchmind] Image work rolled back; text kept')
        media_deferred = True
    env['ir.config_parameter'].sudo().set_param(
        'launchmind_blog.last_received_at', fields.Datetime.now().isoformat()
    )
    # Odoo owns slugs and routing, including the blog portion of the URL.
    base_url = (
        post.website_id.domain or env['ir.config_parameter'].sudo().get_param('web.base.url') or ''
    )
    result = {
        'success': True,
        'action': action,
        'post_id': post.id,
        'post_url': urljoin(base_url.rstrip('/') + '/', post.website_url),
        'article_id': article.article_id,
    }
    if media_deferred:
        result['media_deferred'] = True
    return result


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------


def _safe_eq(a, b):
    """Length-safe string comparison.

    Falls back to a manual constant-time loop because hmac.compare_digest
    raises on unicode strings in some Python builds. Acceptable for v1
    given the short key length.
    """
    if a is None or b is None:
        return False
    if len(a) != len(b):
        return False
    result = 0
    for x, y in zip(a, b):
        result |= ord(x) ^ ord(y)
    return result == 0
