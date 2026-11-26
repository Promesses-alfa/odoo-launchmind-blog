"""Pure measurement rules: bot recognition, beacon bodies, v1 tracking signature.

The platform owns crawler classification and IP verification; this module
only decides which requests receive no human beacon and builds the existing
wire contracts. The API key signs server-side beacons and never reaches a
browser.
"""

import hashlib
import hmac
import ipaddress
import json
import re
from typing import Any, Mapping

from .signing import is_uuid

PLATFORM = 'odoo'
COVERAGE = 'origin-observed'
INTAKE_PATH = '/api/tracking/plugin-view'
HEALTH_PATH = '/api/plugin-health'

# Mirrors isBotUserAgent in apps/web/app/api/tracking/plugin-view/route.ts:
# a request that matches gets no human beacon on either side.
_BOT = re.compile(
    r'bot|crawl|spider|slurp|bingpreview|facebookexternalhit|ia_archiver|wayback|ahrefs|'
    r'semrush|mj12|dotbot|screaming|applebot|linkedinbot|twitterbot|pinterestbot|whatsapp|'
    r'telegram|gptbot|claude|anthropic|ccbot|perplexity|oai-searchbot|chatgpt-user',
    re.IGNORECASE,
)
MAX_UA = 512


def is_bot_user_agent(user_agent: str | None) -> bool:
    return not user_agent or _BOT.search(user_agent) is not None


def sign_v1(api_key: str, timestamp: int, raw: bytes) -> str:
    message = str(timestamp).encode('ascii') + b'.' + raw
    return 'v1=' + hmac.new(api_key.encode('utf-8'), message, hashlib.sha256).hexdigest()


def v1_headers(api_key: str, timestamp: int, raw: bytes) -> dict[str, str]:
    return {
        'Content-Type': 'application/json',
        'X-Launchmind-Timestamp': str(timestamp),
        'X-Launchmind-Signature': sign_v1(api_key, timestamp, raw),
        'X-Launchmind-Source': 'server',
    }


def peer_ip(environ: Mapping[str, Any], proxy_mode: bool) -> str | None:
    """The connection peer, unless Odoo's proxy mode actually rewrote it.

    Odoo applies werkzeug's ProxyFix only in proxy mode, and ProxyFix keeps
    the original peer under ``werkzeug.proxy_fix.orig``. A forwarded header
    without that proven rewrite is never trusted.
    """
    original = environ.get('werkzeug.proxy_fix.orig')
    if proxy_mode and isinstance(original, Mapping):
        candidate = environ.get('REMOTE_ADDR')
    else:
        source = original if isinstance(original, Mapping) else environ
        candidate = source.get('REMOTE_ADDR')
    try:
        return str(ipaddress.ip_address(str(candidate))) if candidate else None
    except ValueError:
        return None


def bot_hit_body(subscription_id: str, path: str, user_agent: str, ip: str | None) -> bytes:
    return json.dumps(
        {
            'type': 'bot_hit',
            'subscription_id': subscription_id,
            'platform': PLATFORM,
            'path': path.split('?')[0].split('#')[0][:512],
            'ua': user_agent[:MAX_UA],
            'ip': ip,
            'source': 'server',
        },
        separators=(',', ':'),
    ).encode('utf-8')


def health_body(
    api_key: str,
    module_version: str,
    odoo_version: str,
    python_version: str,
    post_count: int,
) -> bytes:
    return json.dumps(
        {
            'api_key': api_key,
            'platform': PLATFORM,
            'plugin_version': module_version,
            'odoo_version': odoo_version[:32],
            'python_version': python_version[:32],
            'post_count': post_count,
            'mode': COVERAGE,
        },
        separators=(',', ':'),
    ).encode('utf-8')


def health_recorded(body: bytes) -> bool:
    """Only an explicit recorded:true advances the accepted-health timestamp."""
    try:
        value = json.loads(body)
    except ValueError:
        return False
    return isinstance(value, dict) and value.get('recorded') is True


_SCRIPT = (
    '(function(c){if(window.__lmOdooBeacon)return;window.__lmOdooBeacon=1;'
    'function send(b){b.subscription_id=c.s;b.article_id=c.a;b.platform="odoo";'
    'b.plugin_version=c.v;b.source="client";b.referrer=document.referrer||null;'
    'var d=JSON.stringify(b);try{if(navigator.sendBeacon&&navigator.sendBeacon(c.u,'
    'new Blob([d],{type:"text/plain"})))return}catch(e){}try{fetch(c.u,{method:"POST",'
    'body:d,mode:"no-cors",keepalive:true,credentials:"omit",'
    'headers:{"Content-Type":"text/plain"}})}catch(e){}}'
    'send({event_type:"page_view"});'
    'function click(e){var t=e.target,a=t&&t.closest?t.closest("a[href]"):null;'
    'if(!a)return;var h=a.href;if(!/^https?:\\/\\//i.test(h))return;'
    'send({event_type:"click",target_url:h})}'
    'document.addEventListener("click",click,true);'
    'document.addEventListener("auxclick",function(e){if(e.button===1)click(e)},true)'
    '})(%s);'
)


def beacon_script(intake_url: str, subscription_id: str, article_id: str, version: str) -> str:
    """Public configuration only: intake URL, subscription/source UUIDs, version."""
    if not (is_uuid(subscription_id) and is_uuid(article_id)):
        raise ValueError('Beacon identity must be UUIDs')
    config = json.dumps(
        {'u': intake_url, 's': subscription_id, 'a': article_id, 'v': version},
        ensure_ascii=True,
    )
    # JSON inside an HTML raw-text element: escape what could close or open markup.
    config = config.replace('&', '\\u0026').replace('<', '\\u003c').replace('>', '\\u003e')
    return '<script data-launchmind-beacon="1">%s</script>' % (_SCRIPT % config)
