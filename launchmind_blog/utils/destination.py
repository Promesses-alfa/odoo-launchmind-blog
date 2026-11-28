"""Destination validation shared by settings, receiver and upgrade."""

from typing import Any, Iterable


class DestinationNotConfigured(ValueError):
    pass


DESTINATION_MESSAGE = (
    'Select a website and a matching blog under Settings > Website > Launchmind Blog.'
)
DESTINATION_LANGUAGE_CAPABILITY = 'destination_default_language'


def validate_destination(website_id: int, blog_id: int, blog_website_id: int) -> bool:
    return bool(website_id and blog_id and (not blog_website_id or blog_website_id == website_id))


def parameter_id(value: object) -> int:
    try:
        return int(str(value or '0'))
    except ValueError:
        return 0


def find_destination(env: Any) -> tuple[Any, Any] | None:
    """Return the configured, existing website/blog pair, or no destination."""
    params = env['ir.config_parameter'].sudo()
    website = (
        env['website']
        .sudo()
        .browse(parameter_id(params.get_param('launchmind_blog.website_id')))
        .exists()
    )
    blog = (
        env['blog.blog']
        .sudo()
        .browse(parameter_id(params.get_param('launchmind_blog.blog_id')))
        .exists()
    )
    if not validate_destination(website.id, blog.id, blog.website_id.id if blog else 0):
        return None
    return website, blog


def resolve_destination(env: Any) -> Any:
    destination = find_destination(env)
    if destination is None:
        raise DestinationNotConfigured(DESTINATION_MESSAGE)
    return destination[1]


def destination_default_language(env: Any, selected_website: Any = None) -> str | None:
    """Return the default res.lang code of the destination website, falling back to current."""
    website = selected_website
    if not website:
        destination = find_destination(env)
        website = (
            destination[0] if destination is not None else env['website'].get_current_website()
        )
    if not website or not website.default_lang_id:
        return None
    return website.default_lang_id.code or None


def migration_destination(
    website_id: int, blog_id: int, candidates: Iterable[tuple[int, int]], default_website_id: int
) -> tuple[int, int] | None:
    """Only an entirely empty configuration with one source blog is unambiguous."""
    if website_id or blog_id:
        return None
    blogs = dict(candidates)
    if len(blogs) != 1:
        return None
    selected_blog, blog_website = next(iter(blogs.items()))
    website = blog_website or default_website_id
    return (website, selected_blog) if website else None


def preset_destination(env: Any) -> None:
    params = env['ir.config_parameter'].sudo()
    posts = (
        env['blog.post']
        .sudo()
        .with_context(active_test=False)
        .search(
            [
                '|',
                ('launchmind_article_id', '!=', False),
                '&',
                ('blog_id.name', '=', 'Launchmind Blog'),
                ('website_meta_keywords', 'ilike', 'lm:'),
            ]
        )
    )
    candidates = []
    for post in posts:
        if post.launchmind_article_id or any(
            keyword.strip().startswith('lm:') and keyword.strip()[3:].strip()
            for keyword in (post.website_meta_keywords or '').split(',')
        ):
            candidates.append((post.blog_id.id, post.blog_id.website_id.id))
    default = env['website'].sudo().search([], order='sequence, id', limit=1)
    selected = migration_destination(
        parameter_id(params.get_param('launchmind_blog.website_id')),
        parameter_id(params.get_param('launchmind_blog.blog_id')),
        candidates,
        default.id,
    )
    if selected:
        params.set_param('launchmind_blog.website_id', selected[0])
        params.set_param('launchmind_blog.blog_id', selected[1])
