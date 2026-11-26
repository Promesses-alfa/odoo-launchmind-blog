"""Fill a missing Article owner without replacing native website SEO, and observe views."""

import functools
import json
import time
from html.parser import HTMLParser
from urllib.parse import urlsplit

from lxml import html

from odoo import fields, http
from odoo.addons.website_blog.controllers.main import WebsiteBlog
from odoo.http import request
from odoo.tools import config

from ..models.discovery import PARAM_PRODUCTION, PARAM_TELEMETRY
from ..utils import outbound, telemetry
from ..utils.enrollment import PARAM_API_KEY, PARAM_SUBSCRIPTION
from ..utils.outbound import https_url_allowed
from ..utils.signing import MODULE_VERSION, is_uuid
from ..utils.site_policy import production_origin


class _HeadBoundary(HTMLParser):
    """Locate the real closing tag, not a lookalike in a script or comment."""

    position = None

    def handle_endtag(self, tag):
        if tag == 'head' and self.position is None:
            self.position = self.getpos()


def _has_article(value):
    if isinstance(value, list):
        return any(_has_article(item) for item in value)
    if not isinstance(value, dict):
        return False
    types = value.get('@type', [])
    if isinstance(types, str):
        types = [types]
    if isinstance(types, list) and any(
        kind
        in (
            'Article',
            'BlogPosting',
            'https://schema.org/Article',
            'https://schema.org/BlogPosting',
            'http://schema.org/Article',
            'http://schema.org/BlogPosting',
        )
        for kind in types
    ):
        return True
    return any(_has_article(item) for item in value.values())


def _article_script(page, post):
    document = html.fromstring(page)
    for script in document.xpath('//script[@type]'):
        if script.get('type').strip().lower() != 'application/ld+json':
            continue
        try:
            value = json.loads(script.text or '')
        except ValueError:
            continue
        if _has_article(value):
            return ''
    canonical = document.xpath('//link[@rel="canonical"]/@href')
    if len(canonical) != 1:
        return ''
    article = {
        '@context': 'https://schema.org',
        '@type': 'Article',
        'headline': post.name,
        'description': post.website_meta_description or post.subtitle or '',
        'url': canonical[0],
        'mainEntityOfPage': canonical[0],
    }
    for key, date in [('datePublished', post.post_date), ('dateModified', post.write_date)]:
        if date:
            article[key] = date.isoformat(timespec='seconds') + 'Z'
    if post.author_name:
        # Native stored byline is public with the post; the partner record
        # itself can be private. Do not widen public access with sudo().
        article['author'] = {'@type': 'Person', 'name': post.author_name}
    # JSON lives in an HTML raw-text element: JSON quoting alone is not sufficient.
    encoded = json.dumps(article, ensure_ascii=True).replace('&', '\\u0026')
    encoded = encoded.replace('<', '\\u003c').replace('>', '\\u003e')
    return '<script type="application/ld+json">%s</script>' % encoded


class LaunchmindWebsiteBlog(WebsiteBlog):
    @http.route()
    def blog_post(self, blog, blog_post, tag_id=None, page=1, enable_editor=None, **post):
        response = super().blog_post(
            blog, blog_post, tag_id=tag_id, page=page, enable_editor=enable_editor, **post
        )
        if not (
            blog_post.launchmind_article_id
            and blog_post.active
            and blog_post.website_published
            and blog_post.post_date <= fields.Datetime.now()
            and response.status_code == 200
            and response.mimetype == 'text/html'
        ):
            return response
        # Odoo's normal response finalization does this too. Keep the original
        # response, cookies, status and headers; set_data updates Content-Length.
        response.flatten()
        body = response.get_data(as_text=True)
        head = _HeadBoundary()
        head.feed(body)
        if head.position:
            insertion = _article_script(body, blog_post) + _observe(blog_post, response)
            if insertion:
                line, column = head.position
                offset = sum(len(part) + 1 for part in body.split('\n')[: line - 1]) + column
                response.set_data(body[:offset] + insertion + body[offset:])
        return response


def _observe(post, response):
    """Measurement for an owned, public article response; '' when off or not applicable.

    Humans get a browser beacon (their own IP and location stay theirs); a
    known bot gets none, and its origin-observed request is reported once
    after the response was sent, over HTTPS, never logged or queued.
    """
    params = request.env['ir.config_parameter'].sudo()
    if (params.get_param(PARAM_TELEMETRY) or '').lower() != 'true' or params.get_param(
        'database.is_neutralized'
    ):
        return ''
    origin = production_origin(params.get_param(PARAM_PRODUCTION))
    host = request.httprequest.host.lower()
    if origin and host != urlsplit(origin).netloc:
        return ''
    subscription_id = params.get_param(PARAM_SUBSCRIPTION) or ''
    article_id = post.launchmind_article_id or ''
    intake = (params.get_param('launchmind_blog.api_base') or 'https://launchmind.io').rstrip(
        '/'
    ) + telemetry.INTAKE_PATH
    if not (is_uuid(subscription_id) and is_uuid(article_id) and https_url_allowed(intake)):
        return ''
    user_agent = request.httprequest.user_agent.string or ''
    if telemetry.is_bot_user_agent(user_agent):
        api_key = (params.get_param(PARAM_API_KEY) or '').strip()
        if api_key:
            raw = telemetry.bot_hit_body(
                subscription_id,
                request.httprequest.path,
                user_agent,
                telemetry.peer_ip(request.httprequest.environ, bool(config.get('proxy_mode'))),
            )
            response.call_on_close(functools.partial(_send_crawler_beacon, intake, raw, api_key))
        return ''
    return telemetry.beacon_script(intake, subscription_id, article_id, MODULE_VERSION)


def _send_crawler_beacon(intake, raw, api_key):
    try:
        outbound.send(
            'POST',
            intake,
            data=raw,
            headers=telemetry.v1_headers(api_key, int(time.time()), raw),
            timeout=2.0,
            limit=4096,
        )
    except Exception:  # noqa: BLE001 - best effort; no log, the body holds a crawler IP
        return
