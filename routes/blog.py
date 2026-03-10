"""Blog routes and helpers"""
import os
import re
import logging
import html as html_lib
from datetime import datetime, timezone
from email.utils import format_datetime
from flask import Blueprint, render_template, request, redirect, url_for, Response

blog_bp = Blueprint('blog', __name__)

BLOG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'content', 'blog')


def _slug_to_title(slug: str) -> str:
    return re.sub(r'[-_]+', ' ', (slug or '')).strip().title()


def _safe_iso_z(dt_obj: datetime | None) -> str | None:
    if not dt_obj:
        return None
    if dt_obj.tzinfo:
        dt_obj = dt_obj.astimezone(timezone.utc).replace(tzinfo=None)
    return dt_obj.replace(microsecond=0).isoformat() + 'Z'


def _parse_datetime(raw: str | None) -> datetime | None:
    if not raw:
        return None
    raw = raw.strip()
    if not raw:
        return None

    candidates = [raw]
    if raw.endswith('Z'):
        candidates.append(raw[:-1] + '+00:00')
        candidates.append(raw[:-1])

    for c in candidates:
        try:
            dt_obj = datetime.fromisoformat(c)
            if dt_obj.tzinfo:
                dt_obj = dt_obj.astimezone(timezone.utc).replace(tzinfo=None)
            return dt_obj
        except Exception:
            pass

    for fmt in ('%Y-%m-%d', '%Y/%m/%d', '%d.%m.%Y', '%d-%m-%Y'):
        try:
            return datetime.strptime(raw, fmt)
        except Exception:
            pass

    return None


def _parse_front_matter(raw_text: str) -> tuple[dict, str]:
    """
    Parse minimal YAML-like front matter:
    ---
    title: ...
    description: ...
    date: 2026-03-04
    tags: ai, telegram
    ---
    markdown body...
    """
    lines = raw_text.splitlines()
    if not lines or lines[0].strip() != '---':
        return {}, raw_text

    end_idx = None
    for i in range(1, len(lines)):
        if lines[i].strip() == '---':
            end_idx = i
            break

    if end_idx is None:
        return {}, raw_text

    metadata = {}
    for line in lines[1:end_idx]:
        cleaned = line.strip()
        if not cleaned or cleaned.startswith('#') or ':' not in cleaned:
            continue
        key, value = cleaned.split(':', 1)
        metadata[key.strip().lower()] = value.strip().strip('"').strip("'")

    body = '\n'.join(lines[end_idx + 1:]).lstrip('\n')
    return metadata, body


def _parse_tags(raw_tags: str | None) -> list[str]:
    if not raw_tags:
        return []
    text = raw_tags.strip()
    if text.startswith('[') and text.endswith(']'):
        text = text[1:-1]
    tags = [t.strip().strip('"').strip("'") for t in text.split(',')]
    return [t for t in tags if t]


def _strip_markdown(md_text: str) -> str:
    text = md_text or ''
    text = re.sub(r'```.*?```', ' ', text, flags=re.S)
    text = re.sub(r'`([^`]*)`', r'\1', text)
    text = re.sub(r'!\[[^\]]*\]\([^)]+\)', ' ', text)
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    text = re.sub(r'^\s{0,3}#{1,6}\s*', '', text, flags=re.M)
    text = re.sub(r'^\s*[-*+]\s+', '', text, flags=re.M)
    text = re.sub(r'^\s*\d+\.\s+', '', text, flags=re.M)
    text = re.sub(r'[>#*_~`]', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def _truncate_text(text: str, limit: int) -> str:
    text = (text or '').strip()
    if len(text) <= limit:
        return text
    short = text[:limit].rsplit(' ', 1)[0].strip()
    return (short or text[:limit]).strip() + '...'


def _extract_first_heading(md_text: str) -> str:
    for line in (md_text or '').splitlines():
        m = re.match(r'^\s{0,3}#{1,6}\s+(.+)$', line)
        if m:
            return m.group(1).strip()
    return ''


def _estimate_reading_minutes(text: str) -> int:
    words = len((text or '').split())
    return max(1, (words + 179) // 180)


def _render_inline_markdown(text: str) -> str:
    escaped = html_lib.escape(text or '')

    escaped = re.sub(
        r'`([^`]+)`',
        lambda m: f"<code>{m.group(1)}</code>",
        escaped
    )
    escaped = re.sub(
        r'\[([^\]]+)\]\((https?://[^\s)]+)\)',
        lambda m: (
            f'<a href="{m.group(2)}" target="_blank" rel="noopener noreferrer">'
            f'{m.group(1)}</a>'
        ),
        escaped
    )
    escaped = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', escaped)
    escaped = re.sub(r'(?<!\*)\*([^*]+)\*(?!\*)', r'<em>\1</em>', escaped)
    escaped = re.sub(r'(?<!_)_([^_]+)_(?!_)', r'<em>\1</em>', escaped)
    return escaped


def load_blog_posts():
    """
    Blog post loader.

    Supports:
    1) Front matter markdown format
       ---
       title: ...
       description: ...
       date: 2026-03-04
       author: ...
       tags: ai, telegram
       published: true
       ---
       # Body
    2) Legacy format (first line title, second line description, rest body)
    """
    posts = []
    try:
        if not os.path.isdir(BLOG_DIR):
            return posts

        for name in os.listdir(BLOG_DIR):
            if not name.endswith('.md'):
                continue

            slug = name[:-3]
            path = os.path.join(BLOG_DIR, name)
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    raw_text = f.read()

                metadata, body = _parse_front_matter(raw_text)
                lines = raw_text.splitlines()

                if metadata:
                    title = metadata.get('title') or _extract_first_heading(body) or _slug_to_title(slug)
                    description = metadata.get('description') or metadata.get('excerpt') or ''
                else:
                    title = lines[0].strip() if lines else _slug_to_title(slug)
                    description = lines[1].strip() if len(lines) > 1 else ''
                    body = '\n'.join(lines[2:]) if len(lines) > 2 else ''

                published_raw = metadata.get('published')
                if published_raw is not None and str(published_raw).strip().lower() in {'0', 'false', 'no', 'off'}:
                    continue

                plain_text = _strip_markdown(body)
                if not description:
                    description = _truncate_text(plain_text, 165)

                excerpt = _truncate_text(plain_text, 220)

                try:
                    file_mtime = datetime.utcfromtimestamp(os.path.getmtime(path))
                except Exception:
                    file_mtime = datetime.utcnow()

                published_dt = _parse_datetime(metadata.get('date') or metadata.get('published_at')) or file_mtime
                modified_dt = _parse_datetime(metadata.get('lastmod') or metadata.get('updated_at')) or file_mtime
                reading_minutes = _estimate_reading_minutes(plain_text)

                posts.append({
                    'slug': slug,
                    'title': title,
                    'description': description,
                    'excerpt': excerpt,
                    'body': body,
                    'author': metadata.get('author') or 'BotFactory Team',
                    'tags': _parse_tags(metadata.get('tags')),
                    'cover': metadata.get('cover') or '',
                    'published_at': _safe_iso_z(published_dt),
                    'published_human': published_dt.strftime('%d.%m.%Y'),
                    'lastmod': _safe_iso_z(modified_dt),
                    'reading_minutes': reading_minutes,
                    '_sort_date': published_dt
                })
            except Exception as e:
                logging.error(f"Error reading blog post {name}: {e}")

    except Exception as e:
        logging.error(f"Error loading blog posts: {e}")

    posts.sort(
        key=lambda p: ((p.get('_sort_date') or datetime.min), p.get('slug', '')),
        reverse=True
    )
    for p in posts:
        p.pop('_sort_date', None)
    return posts


def markdown_to_html(md: str) -> str:
    """Markdown -> HTML converter for blog rendering (safe subset)."""
    if not md:
        return ''

    lines = md.replace('\r\n', '\n').replace('\r', '\n').split('\n')
    blocks = []
    paragraph_lines = []
    code_lines = []
    in_ul = False
    in_ol = False
    in_code = False

    def close_lists():
        nonlocal in_ul, in_ol
        if in_ul:
            blocks.append('</ul>')
            in_ul = False
        if in_ol:
            blocks.append('</ol>')
            in_ol = False

    def flush_paragraph():
        nonlocal paragraph_lines
        if paragraph_lines:
            paragraph_text = ' '.join(paragraph_lines).strip()
            if paragraph_text:
                blocks.append(f"<p>{_render_inline_markdown(paragraph_text)}</p>")
            paragraph_lines = []

    for raw_line in lines:
        line = raw_line.rstrip()
        stripped = line.strip()

        if stripped.startswith('```'):
            flush_paragraph()
            close_lists()
            if in_code:
                code_block = html_lib.escape("\n".join(code_lines))
                blocks.append(f"<pre><code>{code_block}</code></pre>")
                code_lines = []
                in_code = False
            else:
                in_code = True
            continue

        if in_code:
            code_lines.append(line)
            continue

        if not stripped:
            flush_paragraph()
            close_lists()
            continue

        header_match = re.match(r'^\s{0,3}(#{1,6})\s+(.+)$', line)
        if header_match:
            flush_paragraph()
            close_lists()
            level = len(header_match.group(1))
            title = _render_inline_markdown(header_match.group(2).strip())
            blocks.append(f"<h{level}>{title}</h{level}>")
            continue

        quote_match = re.match(r'^\s{0,3}>\s+(.+)$', line)
        if quote_match:
            flush_paragraph()
            close_lists()
            blocks.append(f"<blockquote>{_render_inline_markdown(quote_match.group(1).strip())}</blockquote>")
            continue

        ul_match = re.match(r'^\s{0,3}[-*+]\s+(.+)$', line)
        if ul_match:
            flush_paragraph()
            if in_ol:
                blocks.append('</ol>')
                in_ol = False
            if not in_ul:
                blocks.append('<ul>')
                in_ul = True
            blocks.append(f"<li>{_render_inline_markdown(ul_match.group(1).strip())}</li>")
            continue

        ol_match = re.match(r'^\s{0,3}\d+\.\s+(.+)$', line)
        if ol_match:
            flush_paragraph()
            if in_ul:
                blocks.append('</ul>')
                in_ul = False
            if not in_ol:
                blocks.append('<ol>')
                in_ol = True
            blocks.append(f"<li>{_render_inline_markdown(ol_match.group(1).strip())}</li>")
            continue

        close_lists()
        paragraph_lines.append(stripped)

    flush_paragraph()
    close_lists()

    if in_code and code_lines:
        code_block = html_lib.escape("\n".join(code_lines))
        blocks.append(f"<pre><code>{code_block}</code></pre>")

    return '\n'.join(blocks)


@blog_bp.route('/blog')
@blog_bp.route('/blog/')
def blog_index():
    posts = load_blog_posts()
    return render_template('blog_index.html', posts=posts)


@blog_bp.route('/blog/<slug>')
def blog_post(slug):
    posts = load_blog_posts()
    post = next((p for p in posts if p['slug'] == slug), None)
    if not post:
        return redirect(url_for('blog.blog_index'))
    post_html = markdown_to_html(post['body'])

    published = post.get('published_at') or _safe_iso_z(datetime.utcnow())
    modified = post.get('lastmod') or published

    # Related posts: tags overlap + title overlap, fallback by recency
    def score(other):
        if other['slug'] == post['slug']:
            return -1
        title_a = set((post.get('title') or '').lower().split())
        title_b = set((other.get('title') or '').lower().split())
        tags_a = set([t.lower() for t in post.get('tags') or []])
        tags_b = set([t.lower() for t in other.get('tags') or []])
        title_overlap = len(title_a.intersection(title_b))
        tags_overlap = len(tags_a.intersection(tags_b))
        return (tags_overlap * 3) + title_overlap

    sorted_posts = sorted(
        [p for p in posts if p['slug'] != post['slug']],
        key=lambda x: (score(x), x.get('published_at') or x.get('lastmod') or ''),
        reverse=True
    )
    related = sorted_posts[:4]
    return render_template(
        'blog_post.html',
        post=post,
        post_html=post_html,
        related=related,
        published=published,
        modified=modified
    )


@blog_bp.route('/blog/rss.xml')
def blog_rss():
    """Simple RSS feed for the blog."""
    from xml.sax.saxutils import escape as xml_escape

    base = request.url_root.rstrip('/')
    posts = load_blog_posts()
    items = []
    for p in posts[:30]:
        link = f"{base}/blog/{p['slug']}"
        title = xml_escape(p['title'])
        desc = xml_escape(p.get('description', ''))
        raw_date = p.get('published_at') or p.get('lastmod')
        pub_dt = _parse_datetime(raw_date) or datetime.utcnow()
        pub_dt = pub_dt.replace(tzinfo=timezone.utc)
        pubdate = format_datetime(pub_dt)
        items.append(f"""
        <item>
          <title>{title}</title>
          <link>{link}</link>
          <guid>{link}</guid>
          <description>{desc}</description>
          <pubDate>{pubdate}</pubDate>
        </item>
        """)
    rss = f"""<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0">
      <channel>
        <title>BotFactory AI Blog</title>
        <link>{base}/blog</link>
        <description>AI chatbot va messenjer integratsiyalari bo'yicha maqolalar</description>
        {''.join(items)}
      </channel>
    </rss>"""
    return Response(rss, mimetype='application/rss+xml')
