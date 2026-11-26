"""Apply already-validated image bytes without outbound network access."""

import base64
import json
from html import escape
from typing import Any

from lxml import html

from .html_sanitize import sanitize_article_html
from .webhook_values import Media, WebhookRequest, is_safe_cover_url


def _requested_cover(article: WebhookRequest) -> tuple[Media | None, str | None]:
    """The delivered cover entry, or the CSS to apply without one (None preserves)."""
    source = article.cover_source
    if source is None:
        return None, None
    delivered = next(
        (item for item in article.media if item.role == 'cover' and item.source_url == source),
        None,
    )
    if delivered is not None:
        return delivered, None
    if source == '':
        return None, 'none'
    return None, 'url(%s)' % source if is_safe_cover_url(source) else None


def sync_media(env: Any, post: Any, article: WebhookRequest) -> None:
    attachments = env['ir.attachment'].sudo()
    owned = attachments.search(
        [
            ('res_model', '=', 'blog.post'),
            ('res_id', '=', post.id),
            ('launchmind_sha256', '!=', False),
        ]
    )
    if not owned and not article.media and article.cover_source is None:
        return
    root = html.fragment_fromstring(post.content or '', create_parent='div')
    cover = json.loads(post.cover_properties or '{}')
    cover_media, cover_css = _requested_cover(article)
    if cover_media is not None or cover_css is not None:
        cover = {
            'background-color': 'oe_none',
            'opacity': '1',
            'resize_class': 'o_record_has_cover o_half_screen_height o_record_has_cover_top',
        }
        if cover_css is not None:
            cover['background-image'] = cover_css
    changed = False
    for media in article.media:
        images = [img for img in root.iter('img') if img.get('src') == media.source_url]
        is_cover = media is cover_media
        if not images and not is_cover:
            continue
        attachment = owned.filtered(lambda record: record.launchmind_sha256 == media.sha256)[:1]
        if not attachment:
            attachment = attachments.create(
                {
                    'name': 'Launchmind %s' % media.sha256,
                    'datas': base64.b64encode(media.data),
                    'mimetype': media.mime,
                    'res_model': 'blog.post',
                    'res_id': post.id,
                    'public': True,
                    'launchmind_sha256': media.sha256,
                }
            )
            owned |= attachment
        elif not attachment.public:
            attachment.public = True
        image_url = '/web/image/%d' % attachment.id
        if is_cover:
            cover['background-image'] = 'url(%s)' % image_url
            # Native record_cover uses a CSS background on a div, not an img.
            # Keep the alt alongside the URL; our template exposes it as aria-label.
            cover['alt'] = media.alt
        for img in images:
            img.set('src', image_url)
            img.set('alt', media.alt)
            changed = True
    values = {'cover_properties': json.dumps(cover)}
    if changed:
        # Attribute values came from the boundary, so retain Odoo's sanitizer
        # after lxml has escaped and serialized them.
        values['content'] = sanitize_article_html(
            escape(root.text or '')
            + ''.join(html.tostring(child, encoding='unicode') for child in root)
        )
    post.write(values)
    root = html.fragment_fromstring(post.content or '', create_parent='div')
    references = {img.get('src', '').split('?', 1)[0] for img in root.iter('img')}
    background = json.loads(post.cover_properties or '{}').get('background-image')
    for attachment in owned:
        url = '/web/image/%d' % attachment.id
        if url not in references and background != 'url(%s)' % url:
            attachment.unlink()
