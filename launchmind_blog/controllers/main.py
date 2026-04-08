# -*- coding: utf-8 -*-
"""
Launchmind Blog — Webhook Controller

Single public endpoint:

    POST /launchmind-blog/webhook
    Authorization: Bearer <LAUNCHMIND_API_KEY>
    Content-Type: application/json

Receives a single article payload from launchmind.io and creates (or
updates) a corresponding ``blog.post`` record in Odoo's native
``website_blog`` module. The bearer token is verified against the API
key the merchant configured in Settings > Website > Launchmind Blog.

Idempotency
-----------
Each Launchmind article carries a unique ``id``. We store that id in
``blog.post.launchmind_article_id`` so a re-delivered webhook simply
updates the existing post instead of creating a duplicate. This makes
the endpoint safe to retry — important because the publish-to-odoo
cron on launchmind.io will retry failed pushes the next minute.
"""

import json
import logging
import re

from odoo import http, fields
from odoo.http import request, Response

_logger = logging.getLogger(__name__)


def _json_response(payload, status=200):
    """Helper: serialize a dict to a JSON HTTP response."""
    return Response(
        json.dumps(payload),
        status=status,
        headers={'Content-Type': 'application/json; charset=utf-8'},
    )


def _slugify(value):
    """Minimal slugifier — Odoo has its own but we want predictable output."""
    if not value:
        return ''
    value = re.sub(r'[^a-zA-Z0-9\s-]', '', value).strip().lower()
    value = re.sub(r'[\s_-]+', '-', value)
    return value[:200]


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

        # ------------------------------------------------------------------
        # 1. Auth
        # ------------------------------------------------------------------
        ICP = request.env['ir.config_parameter'].sudo()
        configured_key = (ICP.get_param('launchmind_blog.api_key') or '').strip()

        if not configured_key:
            _logger.warning('[Launchmind] Webhook called but no API key is configured')
            return _json_response(
                {'error': 'Launchmind module is not connected on this Odoo. Configure it under Settings > Website > Launchmind Blog.'},
                status=503,
            )

        # Bearer header is the primary auth mechanism. We also accept the
        # api_key inside the body as a fallback (some hosting setups strip
        # custom Authorization headers).
        auth_header = request.httprequest.headers.get('Authorization', '') or ''
        provided_key = ''
        if auth_header.lower().startswith('bearer '):
            provided_key = auth_header[7:].strip()

        # ------------------------------------------------------------------
        # 2. Parse body
        # ------------------------------------------------------------------
        try:
            raw = request.httprequest.get_data(as_text=True) or '{}'
            payload = json.loads(raw)
        except (ValueError, json.JSONDecodeError):
            return _json_response({'error': 'Invalid JSON body'}, status=400)

        if not isinstance(payload, dict):
            return _json_response({'error': 'Body must be a JSON object'}, status=400)

        if not provided_key:
            provided_key = (payload.get('api_key') or '').strip()

        # Constant-time-ish comparison: short keys can leak length but the
        # bigger leak vector here is timing on string comparison, which
        # Python's `==` is not safe against. We at least guarantee both
        # operands have the same shape before comparing.
        if not provided_key or not _safe_eq(provided_key, configured_key):
            _logger.warning('[Launchmind] Webhook called with invalid bearer token')
            return _json_response({'error': 'Unauthorized'}, status=401)

        article = payload.get('article')
        if not isinstance(article, dict):
            return _json_response({'error': 'Missing or invalid article object'}, status=400)

        launchmind_id = article.get('id')
        title = article.get('title')
        content = article.get('content')

        if not launchmind_id or not title or not content:
            return _json_response(
                {'error': 'article must have id, title and content'},
                status=400,
            )

        # ------------------------------------------------------------------
        # 3. Find or create the Launchmind blog
        # ------------------------------------------------------------------
        Blog = request.env['blog.blog'].sudo()
        BlogPost = request.env['blog.post'].sudo()

        blog = Blog.search([('name', '=', 'Launchmind Blog')], limit=1)
        if not blog:
            blog = Blog.create({
                'name': 'Launchmind Blog',
                'subtitle': 'AI-powered SEO articles, automatically published',
            })

        # ------------------------------------------------------------------
        # 4. Idempotent upsert by launchmind_article_id
        # ------------------------------------------------------------------
        # Note: blog.post does not have a launchmind_article_id field by
        # default, so we use the existing `website_meta_keywords` field as
        # a marker (a tag like "lm:<id>") rather than introducing a new
        # column / migration. This keeps the module installable on a fresh
        # Odoo without any DB schema changes.
        marker = 'lm:%s' % launchmind_id
        existing = BlogPost.search([
            ('blog_id', '=', blog.id),
            ('website_meta_keywords', 'ilike', marker),
        ], limit=1)

        slug = article.get('slug') or _slugify(title)
        excerpt = article.get('meta_description') or ''
        author_name = article.get('author') or 'Launchmind'
        cover_image_url = article.get('cover_image_url') or ''
        tags_in = article.get('tags') or []
        if not isinstance(tags_in, list):
            tags_in = []

        # Build the meta keywords string: keep the marker first so we can
        # always re-find this post, then append the article tags.
        meta_keywords_parts = [marker]
        for tag in tags_in:
            if isinstance(tag, str) and tag.strip():
                meta_keywords_parts.append(tag.strip())
        meta_keywords = ', '.join(meta_keywords_parts)[:255]

        # Resolve / create author. blog.post.author_id is res.partner.
        author_partner = request.env['res.partner'].sudo().search(
            [('name', '=', author_name)], limit=1
        )
        if not author_partner:
            author_partner = request.env['res.partner'].sudo().create({
                'name': author_name,
                'company_type': 'person',
            })

        post_vals = {
            'name': title,
            'subtitle': (excerpt or '')[:255],
            'content': content,
            'blog_id': blog.id,
            'author_id': author_partner.id,
            'is_published': True,
            'website_meta_title': title[:255],
            'website_meta_description': (excerpt or '')[:255],
            'website_meta_keywords': meta_keywords,
        }

        # Cover image: Launchmind hosts the image on its own CDN so we just
        # reference the URL directly via cover_properties. Odoo's website
        # blog template renders this as a CSS background-image. We don't
        # need to fetch + store the image binary — public URLs are reliable
        # and avoid bloating the customer's database.
        #
        # cover_properties is a JSON string with 4 keys matching Odoo 18's
        # default schema (see website_blog/models/website_blog_post.py).
        if cover_image_url:
            post_vals['cover_properties'] = json.dumps({
                'background-image': 'url(%s)' % cover_image_url,
                'background-color': 'oe_none',
                'opacity': '1',
                'resize_class': 'o_record_has_cover o_half_screen_height o_record_has_cover_top',
            })

        try:
            if existing:
                existing.write(post_vals)
                post = existing
                action = 'updated'
            else:
                post = BlogPost.create(post_vals)
                action = 'created'
        except Exception as exc:  # pragma: no cover - defensive
            _logger.exception('[Launchmind] Failed to upsert blog post for article %s', launchmind_id)
            return _json_response(
                {'error': 'Failed to save post: %s' % str(exc)},
                status=500,
            )

        # Build the public URL so the launchmind.io tracker can store
        # exactly where the post lives.
        try:
            base_url = ICP.get_param('web.base.url') or ''
            post_url = base_url.rstrip('/') + '/blog/%s/%s-%s' % (blog.id, _slugify(title), post.id)
        except Exception:
            post_url = ''

        ICP.set_param('launchmind_blog.last_received_at', fields.Datetime.now().isoformat())

        return _json_response({
            'success': True,
            'action': action,
            'post_id': post.id,
            'post_url': post_url,
        }, status=200)

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
        return _json_response({
            'ok': True,
            'connected': connected,
            'last_received_at': last_received,
        }, status=200)


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


