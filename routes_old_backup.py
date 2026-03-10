from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, send_file
from flask_login import login_required, current_user
from app import db, csrf
from bot_manager import bot_manager
from models import User, Bot, KnowledgeBase, Payment, ChatHistory, BroadcastMessage, BotCustomer, BotMessage
from werkzeug.utils import secure_filename
import os
import logging
import requests
import re
import html as html_lib
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
import docx
import pandas as pd
from io import BytesIO
from sqlalchemy import text
from rate_limiter import rate_limiter, get_client_ip

main_bp = Blueprint('main', __name__)

@main_bp.route('/')
def index():
    latest_posts = load_blog_posts()[:3]
    return render_template('index.html', latest_posts=latest_posts)

@main_bp.route('/api/webchat', methods=['POST'])
@csrf.exempt
def api_webchat():
    """Frontend web chat endpoint. Returns AI reply as JSON."""
    try:
        client_ip = get_client_ip(request)
        allowed, retry_after = rate_limiter.is_allowed(
            key=f"webchat:{client_ip}",
            limit=30,
            window_seconds=60
        )
        if not allowed:
            return jsonify({
                "ok": False,
                "error": "rate_limited",
                "retry_after": retry_after
            }), 429

        data = request.get_json(silent=True) or {}
        message = (data.get('message') or '').strip()
        if not message:
            return jsonify({"ok": False, "error": "empty_message"}), 400

        # Resolve language preference
        user_lang = 'uz'
        try:
            from flask_login import current_user
            if current_user.is_authenticated and current_user.language:
                user_lang = current_user.language
        except Exception:
            pass

        # Get bot name (generic for site widget)
        bot_name = 'Chatbot Factory AI'

        # Import AI helpers
        from ai import get_ai_response, process_knowledge_base

        # If there is at least one bot, pass its knowledge base
        kb_text = ''
        try:
            first_bot = Bot.query.first()
            if first_bot:
                kb_text = process_knowledge_base(first_bot.id)
                bot_name = first_bot.name or bot_name
        except Exception:
            kb_text = ''

        reply = get_ai_response(message=message, bot_name=bot_name, user_language=user_lang, knowledge_base=kb_text, chat_history='')
        reply = reply or 'Salom! Hozircha javob tayyorlanmoqda. 🤖'
        return jsonify({"ok": True, "reply": reply})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)[:120]}), 500

@main_bp.route('/healthz')
def healthz():
    """Simple health check endpoint for deployment monitoring"""
    try:
        # Optional: lightweight DB check
        from app import db
        db.session.execute(text('SELECT 1'))
        return jsonify({"status": "ok", "db": "ok"}), 200
    except Exception:
        return jsonify({"status": "ok", "db": "degraded"}), 200

@main_bp.route('/enable-miniapp', methods=['POST'])
@login_required
def enable_miniapp():
    """Enable Mini App for all bots (admin-only maintenance endpoint)"""
    if not current_user.is_admin:
        return jsonify({"status": "error", "error": "Forbidden"}), 403

    try:
        bots = Bot.query.all()
        enabled_count = 0
        for bot in bots:
            if not getattr(bot, 'miniapp_enabled', True):
                bot.miniapp_enabled = True
                enabled_count += 1
            elif bot.miniapp_enabled is None:
                bot.miniapp_enabled = True
                enabled_count += 1
        
        # Set all to True just in case
        for bot in bots:
            bot.miniapp_enabled = True
        
        db.session.commit()
        return jsonify({
            "status": "ok",
            "message": f"Mini App enabled for {len(bots)} bots",
            "bots_enabled": len(bots)
        }), 200
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500

@main_bp.route('/dashboard')
@login_required
def dashboard():
    bots = Bot.query.filter_by(user_id=current_user.id).all()
    bot_count = len(bots)
    
    # Get subscription info
    subscription_info = {
        'type': current_user.subscription_type,
        'end_date': current_user.subscription_end_date,
        'active': current_user.subscription_active(),
        'can_create': current_user.can_create_bot()
    }
    
    return render_template('dashboard.html', bots=bots, bot_count=bot_count, 
                         subscription_info=subscription_info)

@main_bp.route('/admin')
@main_bp.route('/admin/')
@login_required
def admin():
    if not current_user.is_admin:
        flash('Sizda admin huquqi yo\'q!', 'error')
        return redirect(url_for('main.dashboard'))
    # Build admin dashboard context
    users = User.query.all()
    payments = Payment.query.order_by(Payment.created_at.desc()).limit(50).all()
    bots = Bot.query.all()
    
    # Statistics
    stats = {
        'total_users': User.query.count(),
        'active_subscriptions': User.query.filter(User.subscription_type.in_(['starter', 'basic', 'premium'])).count(),
        'total_bots': Bot.query.count(),
        'total_payments': Payment.query.filter_by(status='completed').count(),
        'monthly_revenue': Payment.query.filter(
            Payment.status == 'completed',
            Payment.created_at >= datetime.utcnow() - timedelta(days=30)
        ).count()
    }
    
    # Get broadcast messages
    broadcasts = BroadcastMessage.query.order_by(BroadcastMessage.created_at.desc()).limit(10).all()
    
    # Get recent chat history
    chat_history = ChatHistory.query.order_by(ChatHistory.created_at.desc()).limit(50).all()
    
    return render_template('admin.html', users=users, payments=payments, 
                         bots=bots, stats=stats, broadcasts=broadcasts, chat_history=chat_history)
# ================= SEO: sitemap.xml and robots.txt =================
@main_bp.route('/sitemap.xml')
def sitemap_xml():
    """Generate a simple sitemap for key pages"""
    from flask import Response
    base = request.url_root.rstrip('/')
    urls = [
        f"{base}/",
        f"{base}/dashboard",
        f"{base}/admin",
        f"{base}/login",
        f"{base}/register",
        f"{base}/help",
    ]
    # Add blog posts
    try:
        for p in load_blog_posts():
            urls.append({
                'loc': f"{base}/blog/{p['slug']}",
                'lastmod': p.get('lastmod')
            })
    except Exception:
        pass
    xml = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
    ]
    for u in urls:
        xml.append('<url>')
        if isinstance(u, dict):
            xml.append(f"<loc>{u['loc']}</loc>")
            if u.get('lastmod'):
                xml.append(f"<lastmod>{u['lastmod']}</lastmod>")
        else:
            xml.append(f'<loc>{u}</loc>')
        xml.append('</url>')
    xml.append('</urlset>')
    return Response("\n".join(xml), mimetype='application/xml')

@main_bp.route('/robots.txt')
def robots_txt():
    """Basic robots.txt allowing all and pointing to sitemap"""
    from flask import Response
    base = request.url_root.rstrip('/')
    content = f"""User-agent: *
Allow: /
Sitemap: {base}/sitemap.xml
"""
    return Response(content, mimetype='text/plain')

# ===================== Blog =====================
BLOG_DIR = os.path.join(os.path.dirname(__file__), 'content', 'blog')

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

@main_bp.route('/blog')
def blog_index():
    posts = load_blog_posts()
    return render_template('blog_index.html', posts=posts)

@main_bp.route('/blog/<slug>')
def blog_post(slug):
    posts = load_blog_posts()
    post = next((p for p in posts if p['slug'] == slug), None)
    if not post:
        return redirect(url_for('main.blog_index'))
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

@main_bp.route('/blog/rss.xml')
def blog_rss():
    """Simple RSS feed for the blog."""
    from flask import Response
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

# ===================== Help / Getting Started =====================
@main_bp.route('/help')
def help_getting_started():
    return render_template('help_getting_started.html')
# ===================== Admin: Delete Bot / User =====================
@main_bp.route('/admin/delete-bot/<int:bot_id>', methods=['POST'])
@login_required
def admin_delete_bot(bot_id):
    """Admin uchun: botni to'xtatib, barcha bog'liq ma'lumotlari bilan o'chirish
    Xavfsizlik: faqat admin. Foydalanuvchi o'z botini o'chirmaydi (admin paneldan).
    """
    if not current_user.is_admin:
        flash('Ruxsat yo\'q', 'error')
        return redirect(url_for('main.dashboard'))

    try:
        bot = Bot.query.get_or_404(bot_id)

        # Stop platform runner safely
        platform = (bot.platform or '').lower()
        try:
            if platform == 'telegram':
                bot_manager.stop_bot_polling(bot.id, 'telegram')
            elif platform == 'instagram':
                from instagram_bot import instagram_manager
                instagram_manager.stop_bot(bot.id)
            elif platform == 'whatsapp':
                from whatsapp_bot import whatsapp_manager
                whatsapp_manager.stop_bot(bot.id)
        except Exception as e:
            logging.warning(f"Bot stop during delete warning: {e}")

        # Delete related records
        try:
            ChatHistory.query.filter_by(bot_id=bot.id).delete(synchronize_session=False)
        except Exception:
            pass
        try:
            BotCustomer.query.filter_by(bot_id=bot.id).delete(synchronize_session=False)
        except Exception:
            pass
        try:
            BotMessage.query.filter_by(bot_id=bot.id).delete(synchronize_session=False)
        except Exception:
            pass
        try:
            BroadcastMessage.query.filter_by(bot_id=bot.id).delete(synchronize_session=False)
        except Exception:
            pass

        # Finally delete bot
        db.session.delete(bot)
        db.session.commit()
        flash('Bot va bog\'liq ma\'lumotlar o\'chirildi', 'success')
    except Exception as e:
        logging.error(f"Admin delete bot error: {e}")
        db.session.rollback()
        flash('O\'chirishda xatolik', 'error')

    return redirect(url_for('main.dashboard'))

@main_bp.route('/admin/delete-user/<int:user_id>', methods=['POST'])
@login_required
def admin_delete_user(user_id):
    """Admin uchun: foydalanuvchini va uning botlarini o'chirish.
    Admin rolli foydalanuvchilarni saqlab qolamiz.
    """
    if not current_user.is_admin:
        flash('Ruxsat yo\'q', 'error')
        return redirect(url_for('main.dashboard'))

    user = User.query.get_or_404(user_id)
    if getattr(user, 'is_admin', False):
        flash('Admin foydalanuvchini o\'chirib bo\'lmaydi', 'warning')
        return redirect(url_for('main.dashboard'))

    try:
        # Delete user's bots via admin_delete_bot logic (stop + cascade)
        bots = Bot.query.filter_by(user_id=user.id).all()
        for b in bots:
            try:
                # Reuse deletion steps inline to keep single transaction
                platform = (b.platform or '').lower()
                try:
                    if platform == 'telegram':
                        bot_manager.stop_bot_polling(b.id, 'telegram')
                    elif platform == 'instagram':
                        from instagram_bot import instagram_manager
                        instagram_manager.stop_bot(b.id)
                    elif platform == 'whatsapp':
                        from whatsapp_bot import whatsapp_manager
                        whatsapp_manager.stop_bot(b.id)
                except Exception:
                    pass
                ChatHistory.query.filter_by(bot_id=b.id).delete(synchronize_session=False)
                BotCustomer.query.filter_by(bot_id=b.id).delete(synchronize_session=False)
                try:
                    BotMessage.query.filter_by(bot_id=b.id).delete(synchronize_session=False)
                except Exception:
                    pass
                try:
                    BroadcastMessage.query.filter_by(bot_id=b.id).delete(synchronize_session=False)
                except Exception:
                    pass
                db.session.delete(b)
            except Exception as inner_e:
                logging.error(f"Delete user bot error: {inner_e}")

        # Finally delete user
        db.session.delete(user)
        db.session.commit()
        flash('Foydalanuvchi va uning botlari o\'chirildi', 'success')
    except Exception as e:
        logging.error(f"Admin delete user error: {e}")
        db.session.rollback()
        flash('O\'chirishda xatolik', 'error')

    return redirect(url_for('main.dashboard'))


@main_bp.route('/admin/test_message', methods=['POST'])
@login_required
def test_message():
    if not current_user.is_admin:
        flash('Sizda admin huquqi yo\'q!', 'error')
        return redirect(url_for('main.dashboard'))
    
    try:
        from telegram_bot import send_admin_message_to_user
        
        test_message_text = "🧪 TEST XABARI\n\nSalom! Bu BotFactory AI dan test xabari.\n\n✅ Telegram bot to'g'ri ishlayapti!\n\n📅 Vaqt: " + datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Admin foydalanuvchining telegram_id sini olish
        if current_user.telegram_id:
            result = send_admin_message_to_user(current_user.telegram_id, test_message_text)
            if result:
                flash('✅ Test xabari muvaffaqiyatli yuborildi!', 'success')
            else:
                flash('❌ Test xabarini yuborishda xatolik yuz berdi!', 'error')
        else:
            flash('❌ Telegram ID topilmadi. Avval botga /start buyrug\'ini yuboring!', 'error')
            
    except Exception as e:
        flash(f'❌ Xatolik: {str(e)}', 'error')
        
    return redirect(url_for('main.admin'))

# =============== Instagram Diagnostics ===============
@main_bp.route('/admin/api/instagram/diagnostics/<int:bot_id>')
@login_required
def instagram_diagnostics(bot_id):
    """Simple diagnostics to verify Instagram token and show webhook URL.
    Returns JSON with checks: token_present, token_valid (via /me), webhook_url.
    """
    if not current_user.is_admin:
        return jsonify({'error': 'Access denied'}), 403
    try:
        bot = Bot.query.get_or_404(bot_id)
        if (bot.platform or '').lower() != 'instagram':
            return jsonify({'error': 'Not an Instagram bot'}), 400
        info = {
            'bot_id': bot_id,
            'platform': 'instagram',
            'token_present': bool(bot.instagram_token),
            'token_valid': False,
            'webhook_url': url_for('instagram.instagram_webhook', bot_id=bot_id, _external=True),
            'webhook_verify_param_example': '?hub.verify_token=YOUR_VERIFY_TOKEN&hub.challenge=123',
        }
        # Minimal token validation: call Graph /me
        if bot.instagram_token:
            try:
                resp = requests.get('https://graph.facebook.com/v18.0/me', params={'access_token': bot.instagram_token}, timeout=15)
                j = {}
                try:
                    j = resp.json()
                except Exception:
                    j = {'raw': resp.text}
                info['graph_status_code'] = resp.status_code
                info['graph_response'] = j
                if resp.status_code == 200 and j.get('id'):
                    info['token_valid'] = True
            except Exception as e:
                info['graph_error'] = str(e)
        return jsonify(info)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@main_bp.route('/admin/set_telegram_id', methods=['POST'])
@login_required
def set_telegram_id():
    if not current_user.is_admin:
        flash('Sizda admin huquqi yo\'q!', 'error')
        return redirect(url_for('main.dashboard'))
    
    try:
        telegram_id = request.form.get('telegram_id')
        if telegram_id and telegram_id.isdigit():
            # Mavjud foydalanuvchini tekshirish
            existing_user = User.query.filter_by(telegram_id=telegram_id).first()
            
            if existing_user and existing_user.id != current_user.id:
                if existing_user.username.startswith('tg_'):
                    # Avtomatik yaratilgan foydalanuvchini o'chirish
                    # Avval uning barcha ma'lumotlarini admin ga ko'chirish
                    
                    # Botlarni ko'chirish
                    from models import Bot
                    for bot in existing_user.bots:
                        bot.user_id = current_user.id
                    
                    # Chat history va boshqa ma'lumotlarni ko'chirish kerak emas
                    # chunki ular admin bilan bog'liq emas
                    
                    # Eski foydalanuvchini o'chirish
                    db.session.delete(existing_user)
                    db.session.flush()  # O'chirish operatsiyasini bajarish
                    
                    flash(f'✅ Telegram ID {telegram_id} ga ega avtomatik foydalanuvchi admin bilan birlashtirildi!', 'info')
                else:
                    flash(f'❌ Telegram ID {telegram_id} boshqa haqiqiy foydalanuvchi tomonidan ishlatilmoqda!', 'error')
                    return redirect(url_for('main.admin'))
            
            # Admin ga Telegram ID ni tayinlash
            current_user.telegram_id = telegram_id
            db.session.commit()
            flash('✅ Telegram ID muvaffaqiyatli saqlandi!', 'success')
        else:
            flash('❌ To\'g\'ri Telegram ID kiriting (faqat raqamlar)!', 'error')
            
    except Exception as e:
        db.session.rollback()
        flash(f'❌ Xatolik: {str(e)}', 'error')
        
    return redirect(url_for('main.admin'))

@main_bp.route('/admin/export-chat-history')
@login_required
def export_chat_history():
    """Export chat history to Excel"""
    if not current_user.is_admin:
        flash('Sizda admin huquqi yo\'q!', 'error')
        return redirect(url_for('main.dashboard'))
    
    try:
        # Get all chat history
        chat_data = ChatHistory.query.order_by(ChatHistory.created_at.desc()).all()
        
        # Prepare data for Excel
        export_data = []
        for chat in chat_data:
            # Get bot name
            bot = Bot.query.get(chat.bot_id)
            bot_name = bot.name if bot else 'Noma\'lum bot'
            
            export_data.append({
                'Vaqt': chat.created_at.strftime('%d.%m.%Y %H:%M:%S'),
                'Bot nomi': bot_name,
                'Platform': bot.platform if bot else 'Noma\'lum',
                'Telegram ID': chat.user_telegram_id or '',
                'Instagram ID': chat.user_instagram_id or '',
                'WhatsApp raqami': chat.user_whatsapp_number or '',
                'Foydalanuvchi xabari': chat.message or '',
                'Bot javobi': chat.response or '',
                'Til': chat.language or 'uz'
            })
        
        if not export_data:
            flash('Eksport qilish uchun yozishmalar mavjud emas!', 'warning')
            return redirect(url_for('main.admin'))
        
        # Create Excel file
        df = pd.DataFrame(export_data)
        
        # Create a BytesIO object
        output = BytesIO()
        
        # Write to Excel
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Bot Yozishmalari', index=False)
        
        output.seek(0)
        
        # Generate filename with current date
        filename = f"bot_yozishmalari_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=filename
        )
        
    except Exception as e:
        flash(f'Eksport qilishda xatolik: {str(e)}', 'error')
        return redirect(url_for('main.admin'))

@main_bp.route('/settings')
@login_required
def settings():
    """User settings page"""
    return render_template('settings.html')

@main_bp.route('/settings/notifications', methods=['POST'])
@login_required
def update_notification_settings():
    """Update notification settings"""
    admin_chat_id = request.form.get('admin_chat_id', '').strip()
    notification_channel = request.form.get('notification_channel', '').strip()
    notifications_enabled = 'notifications_enabled' in request.form
    
    try:
        current_user.admin_chat_id = admin_chat_id if admin_chat_id else None
        current_user.notification_channel = notification_channel if notification_channel else None
        current_user.notifications_enabled = notifications_enabled
        
        db.session.commit()
        
        # Test notification yuborish
        if notifications_enabled and admin_chat_id:
            from notification_service import notification_service
            if notification_service.test_notification(admin_chat_id):
                flash('Bildirishnoma sozlamalari saqlandi va test xabar yuborildi!', 'success')
            else:
                flash('Sozlamalar saqlandi, lekin test xabarni yuborishda xatolik!', 'warning')
        else:
            flash('Bildirishnoma sozlamalari muvaffaqiyatli saqlandi!', 'success')
            
    except Exception as e:
        flash(f'Sozlamalarni saqlashda xatolik: {str(e)}', 'error')
    
    return redirect(url_for('main.settings'))

@main_bp.route('/admin/cleanup-chat-history', methods=['POST'])
@login_required
def cleanup_chat_history():
    """Clean up old chat history to reduce database size"""
    if not current_user.is_admin:
        flash('Sizda admin huquqi yo\'q!', 'error')
        return redirect(url_for('main.dashboard'))
    
    try:
        # Keep only last 1000 entries to reduce database load
        total_count = ChatHistory.query.count()
        
        if total_count > 1000:
            # Get IDs of records to keep (latest 1000)
            keep_ids = db.session.query(ChatHistory.id).order_by(ChatHistory.created_at.desc()).limit(1000).subquery()
            
            # Delete old records
            deleted_count = ChatHistory.query.filter(~ChatHistory.id.in_(keep_ids)).delete(synchronize_session=False)
            db.session.commit()
            
            flash(f'Eski yozishmalar tozalandi! {deleted_count} ta yozuv o\'chirildi, {1000} ta oxirgi yozuv saqlandi.', 'success')
        else:
            flash(f'Tozalash kerak emas. Jami {total_count} ta yozishma mavjud (1000 dan kam).', 'info')
    
    except Exception as e:
        flash(f'Tozalashda xatolik: {str(e)}', 'error')
    
    return redirect(url_for('main.admin'))

def handle_bulk_product_upload(file, bot_id):
    """Excel/CSV orqali ko'p mahsulot qo'shish helper funksiyasi"""
    try:
        # Fayl format tekshirish
        filename = file.filename or ''
        file_ext = os.path.splitext(filename)[1].lower()
        
        # Fayl stream'ini pandas'ga o'qish
        if file_ext == '.csv':
            df = pd.read_csv(file.stream)
        else:
            df = pd.read_excel(file.stream)
        
        # Ustunlar nomini standartlashtirish
        expected_columns = ['mahsulot_nomi', 'narx', 'tavsif', 'rasm_url']
        if len(df.columns) >= 1:
            # Birinchi 4 ta ustunni standart nomlarga o'zgartirish
            new_columns = {}
            for i, col in enumerate(df.columns[:4]):
                if i < len(expected_columns):
                    new_columns[col] = expected_columns[i]
            df.rename(columns=new_columns, inplace=True)
        
        # Bo'sh qatorlarni olib tashlash
        df = df.dropna(subset=['mahsulot_nomi'])
        
        added_count = 0
        errors = []
        
        for idx, row in df.iterrows():
            row_num = int(idx) + 2  # Excel qator raqami
            try:
                product_name = str(row.get('mahsulot_nomi', '')).strip()
                if not product_name or product_name == 'nan':
                    continue
                
                product_price = str(row.get('narx', '')).strip()
                if product_price == 'nan':
                    product_price = ''
                
                product_description = str(row.get('tavsif', '')).strip()
                if product_description == 'nan':
                    product_description = ''
                
                product_image_url = str(row.get('rasm_url', '')).strip()
                if product_image_url == 'nan':
                    product_image_url = ''
                
                # Mahsulot ma'lumotlarini birlashtirish
                content_parts = [f"Mahsulot: {product_name}"]
                if product_price:
                    content_parts.append(f"Narx: {product_price}")
                if product_description:
                    content_parts.append(f"Tavsif: {product_description}")
                if product_image_url:
                    content_parts.append(f"Rasm: {product_image_url}")
                
                content = "\n".join(content_parts)
                
                # Mahsulotni bazaga qo'shish
                knowledge = KnowledgeBase()
                knowledge.bot_id = bot_id
                knowledge.content = content
                knowledge.filename = None
                knowledge.content_type = 'product'
                knowledge.source_name = product_name
                
                db.session.add(knowledge)
                added_count += 1
                
            except Exception as row_error:
                errors.append(f"Qator {row_num}: {str(row_error)}")
        
        # Saqlash
        db.session.commit()
        
        if added_count > 0:
            flash(f'{added_count} ta mahsulot muvaffaqiyatli qo\'shildi!', 'success')
        if errors:
            error_text = '; '.join(errors[:5])  # Birinchi 5 ta xatolikni ko'rsatish
            flash(f'Ba\'zi qatorlarda xatoliklar: {error_text}', 'warning')
        
    except Exception as e:
        flash(f'Excel/CSV fayl qayta ishlashda xatolik: {str(e)}', 'error')
    
    return redirect(url_for('main.edit_bot', bot_id=bot_id))

@main_bp.route('/download-sample-excel')
@login_required  
def download_sample_excel():
    """Namuna Excel faylini yuklab olish"""
    try:
        # Namuna ma'lumotlar
        sample_data = {
            'mahsulot_nomi': [
                'Zip paket 4x6', 
                'Telefon g\'ilof', 
                'USB kabel',
                'Bluetooth quloqchin',
                'Power bank 10000mAh'
            ],
            'narx': [
                '3000 so\'m',
                '25000 so\'m', 
                '15000 so\'m',
                '85000 so\'m',
                '120000 so\'m'
            ],
            'tavsif': [
                'Suv o\'tkazmaydigan zip paket, zo\'r sifatli',
                'Telefon uchun himoya g\'ilofi, turli ranglar',
                'Tez zaryadlash USB kabeli, 1 metr',
                'Simsiz bluetooth quloqchin, sifatli ovoz',
                'Portativ zaryadlovchi, ko\'p marta foydalanish mumkin'
            ],
            'rasm_url': [
                'https://example.com/zip-paket.jpg',
                'https://example.com/telefon-gilof.jpg', 
                'https://example.com/usb-kabel.jpg',
                'https://example.com/bluetooth-quloqchin.jpg',
                'https://example.com/power-bank.jpg'
            ]
        }
        
        # DataFrame yaratish
        df = pd.DataFrame(sample_data)
        
        # BytesIO obyekt yaratish
        output = BytesIO()
        
        # Excel ga yozish
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Mahsulotlar', index=False)
        
        output.seek(0)
        
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name='mahsulotlar_namuna.xlsx'
        )
        
    except Exception as e:
        flash(f'Namuna fayl yaratishda xatolik: {str(e)}', 'error')
        return redirect(url_for('main.dashboard'))

@main_bp.route('/admin/broadcast', methods=['POST'])
@login_required
def send_broadcast():
    if not current_user.is_admin:
        flash('Sizda admin huquqi yo\'q!', 'error')
        return redirect(url_for('main.dashboard'))
    
    message_text = request.form.get('message_text')
    target_type = request.form.get('target_type', 'all')
    segment = request.form.get('segment', '').strip()
    
    if not message_text:
        flash('Xabar matni kiritilishi shart!', 'error')
        return redirect(url_for('main.admin'))
    
    # Create broadcast message record
    broadcast = BroadcastMessage()
    broadcast.admin_id = current_user.id
    broadcast.message_text = message_text
    broadcast.target_type = target_type
    broadcast.status = 'sending'
    broadcast.sent_at = datetime.utcnow()
    
    db.session.add(broadcast)
    db.session.commit()
    
    # Send messages
    try:
        sent_count = send_broadcast_messages(broadcast.id, message_text, target_type, segment)
        
        # Update broadcast record
        broadcast.sent_count = sent_count
        broadcast.status = 'completed'
        db.session.commit()
        
        flash(f'Xabar muvaffaqiyatli yuborildi! {sent_count} ta foydalanuvchiga yetkazildi.', 'success')
    except Exception as e:
        broadcast.status = 'failed'
        db.session.commit()
        flash('Xabar yuborishda xatolik yuz berdi!', 'error')
    
    return redirect(url_for('main.admin'))

@main_bp.route('/admin/change-subscription', methods=['POST'])
@login_required
def change_user_subscription():
    if not current_user.is_admin:
        flash('Sizda admin huquqi yo\'q!', 'error')
        return redirect(url_for('main.dashboard'))
    
    user_id = request.form.get('user_id')
    subscription_type = request.form.get('subscription_type')
    subscription_duration = request.form.get('subscription_duration', '30')  # Default 30 days
    
    if not user_id or not subscription_type:
        flash('Xatolik: Ma\'lumotlar to\'liq emas!', 'error')
        return redirect(url_for('main.admin'))
    
    user = User.query.get_or_404(user_id)
    
    # Don't allow changing admin subscription
    if user.subscription_type == 'admin':
        flash('Xatolik: Admin obunasini o\'zgartirib bo\'lmaydi!', 'error')
        return redirect(url_for('main.admin'))
    
    # Handle trial_14 as a special case
    if subscription_type == 'trial_14':
        user.subscription_type = 'basic'  # Give basic features during trial
        user.subscription_end_date = datetime.utcnow() + timedelta(days=7)
        subscription_name = '7 kun test'
        duration_text = '7 kun'
    elif subscription_type == 'free':
        user.subscription_type = 'free'
        user.subscription_end_date = None
        subscription_name = 'Bepul'
        duration_text = 'cheksiz'
    else:
        # Set new subscription
        user.subscription_type = subscription_type
        # Calculate end date based on duration
        days = int(subscription_duration)
        user.subscription_end_date = datetime.utcnow() + timedelta(days=days)
        subscription_names = {
            'starter': 'Standart',
            'basic': 'Standart',
            'premium': 'Premium'
        }
        subscription_name = subscription_names.get(subscription_type, subscription_type)
        duration_text = f'{subscription_duration} kun'
    
    try:
        db.session.commit()
        
        # Create payment record for manual subscription change
        payment = Payment()
        payment.user_id = user.id
        payment.amount = 0  # Manual change by admin
        payment.method = 'Admin'
        payment.status = 'completed'
        payment.subscription_type = subscription_type
        payment.transaction_id = f'ADMIN_{current_user.id}_{datetime.utcnow().strftime("%Y%m%d%H%M%S")}'
        
        db.session.add(payment)
        db.session.commit()
        
        flash(f'{user.username} foydalanuvchisining obunasi {subscription_name} ga o\'zgartirildi ({duration_text})', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Obunani o\'zgartirishda xatolik yuz berdi!', 'error')
    
    return redirect(url_for('main.admin'))

def send_broadcast_messages(broadcast_id, message_text, target_type, segment: str = ""):
    """Send broadcast message to users"""
    sent_count = 0
    sent_keys = set()  # avoid duplicate sends across sources

    # 1) Platform Users (with telegram_id)
    if target_type == 'customers':
        # paying customers only
        base_q = User.query.filter(User.subscription_type.in_(['starter', 'basic', 'premium']))
    else:
        base_q = User.query

    # Apply segment filters to platform users
    now = datetime.utcnow()
    if segment == 'trial_14':
        # Free users within first 14-15 days
        users = base_q.filter(
            User.subscription_type == 'free',
            (
                # If end_date exists, use it
                (User.subscription_end_date != None) & (User.subscription_end_date > now) & (User.subscription_end_date <= now + timedelta(days=1))
            ) | (
                # Legacy: compute approx from start/created_at
                (User.subscription_end_date == None)
            )
        ).all()
    elif segment == 'active_30d':
        # Users who interacted in last 30 days (have ChatHistory)
        from models import ChatHistory
        cutoff = now - timedelta(days=30)
        subq = db.session.query(ChatHistory.user_telegram_id).filter(ChatHistory.created_at >= cutoff).subquery()
        users = base_q.filter(User.telegram_id.isnot(None), User.telegram_id.in_(subq)).all()
    elif segment == 'paid':
        users = base_q.filter(User.subscription_type.in_(['starter', 'basic', 'premium'])).all()
    elif segment == 'unpaid':
        users = base_q.filter(User.subscription_type == 'free').all()
    else:
        users = base_q.filter(User.telegram_id.isnot(None)).all()

    try:
        from telegram_bot import send_admin_message_to_user, send_message_to_bot_customer
        # Send to platform users first
        for user in users:
            if not user.telegram_id:
                continue
            key = ('user', str(user.telegram_id))
            if key in sent_keys:
                continue
            try:
                if send_admin_message_to_user(user.telegram_id, message_text):
                    sent_keys.add(key)
                    sent_count += 1
            except Exception:
                continue

        # 2) Bot end-users (BotCustomer) — telegram/instagram/whatsapp
        if target_type != 'customers':  # only include bot users for 'all'
            cust_q = BotCustomer.query.filter(BotCustomer.is_active.is_(True))
            if segment == 'active_30d':
                cust_q = cust_q.filter(BotCustomer.last_interaction >= now - timedelta(days=30))
            customers = cust_q.all()
            for c in customers:
                key = ('bot', c.bot_id, c.platform, str(c.platform_user_id))
                # Skip if this user already received via platform user telegram_id
                if ('user', str(c.platform_user_id)) in sent_keys or key in sent_keys:
                    continue
                try:
                    ok = False
                    if c.platform == 'telegram':
                        ok = send_message_to_bot_customer(c.bot_id, c.platform, str(c.platform_user_id), f"📢 Admin xabari:\n\n{message_text}")
                    elif c.platform == 'instagram':
                        from instagram_bot import send_message_to_instagram_customer
                        ok = send_message_to_instagram_customer(c.bot_id, str(c.platform_user_id), f"📢 Admin xabari:\n\n{message_text}")
                    elif c.platform == 'whatsapp':
                        from whatsapp_bot import send_message_to_whatsapp_customer
                        ok = send_message_to_whatsapp_customer(c.bot_id, str(c.platform_user_id), f"📢 Admin xabari:\n\n{message_text}")
                    if ok:
                        sent_keys.add(key)
                        sent_count += 1
                except Exception:
                    continue
    except Exception:
        pass

    return sent_count

@main_bp.route('/bot/create', methods=['GET', 'POST'])
@login_required
def create_bot():
    if not current_user.can_create_bot():
        flash('Siz maksimal bot soni yaratdingiz!', 'error')
        return redirect(url_for('main.dashboard'))
    
    if request.method == 'POST':
        name = request.form.get('name')
        platform = request.form.get('platform', 'Telegram')
        telegram_token = request.form.get('telegram_token')
        instagram_token = request.form.get('instagram_token')
        whatsapp_token = request.form.get('whatsapp_token')
        whatsapp_phone_id = request.form.get('whatsapp_phone_id')
        
        if not name:
            flash('Bot nomi kiritilishi shart!', 'error')
            return render_template('bot_create.html')
        
        bot = Bot()
        bot.user_id = current_user.id
        bot.name = name
        bot.platform = platform
        bot.telegram_token = telegram_token
        bot.instagram_token = instagram_token
        bot.whatsapp_token = whatsapp_token
        bot.whatsapp_phone_id = whatsapp_phone_id
        
        # Suhbat kuzatuvi sozlamalarini saqlash
        admin_chat_id = request.form.get('admin_chat_id')
        notification_channel = request.form.get('notification_channel')
        notifications_enabled = bool(request.form.get('notifications_enabled'))
        
        if admin_chat_id:
            current_user.admin_chat_id = admin_chat_id.strip()
        if notification_channel:
            current_user.notification_channel = notification_channel.strip()
        current_user.notifications_enabled = notifications_enabled
        
        db.session.add(bot)
        db.session.commit()
        
        # Platform uchun avtomatik ishga tushirish (central manager)
        if platform == 'Telegram' and telegram_token:
            try:
                bot_manager.start_bot_polling(bot)
                bot.is_active = True
                db.session.commit()
                flash('Telegram bot muvaffaqiyatli yaratildi va ishga tushirildi!', 'success')
            except Exception as e:
                logging.error(f"Telegram botni ishga tushirishda xato: {e}")
                flash('Bot yaratildi, lekin token noto\'g\'ri yoki ishga tushirishda muammo!', 'warning')
        elif platform == 'Instagram' and instagram_token:
            try:
                from instagram_bot import start_instagram_bot_automatically
                success = start_instagram_bot_automatically(bot.id, instagram_token)
                if success:
                    bot.is_active = True
                    db.session.commit()
                    flash('Instagram bot muvaffaqiyatli yaratildi va ishga tushirildi!', 'success')
                else:
                    flash('Bot yaratildi, lekin token noto\'g\'ri yoki ishga tushirishda muammo!', 'warning')
            except Exception as e:
                flash(f'Bot yaratildi, lekin aktivlashtirish xatoligi: {str(e)}', 'warning')
        elif platform == 'WhatsApp' and whatsapp_token and whatsapp_phone_id:
            try:
                from whatsapp_bot import start_whatsapp_bot_automatically
                success = start_whatsapp_bot_automatically(bot.id, whatsapp_token, whatsapp_phone_id)
                if success:
                    bot.is_active = True
                    db.session.commit()
                    flash('WhatsApp bot muvaffaqiyatli yaratildi va ishga tushirildi!', 'success')
                else:
                    flash('Bot yaratildi, lekin token noto\'g\'ri yoki ishga tushirishda muammo!', 'warning')
            except Exception as e:
                flash(f'Bot yaratildi, lekin aktivlashtirish xatoligi: {str(e)}', 'warning')
        else:
            flash('Bot muvaffaqiyatli yaratildi!', 'success')
        
        return redirect(url_for('main.dashboard'))
    
    return render_template('bot_create.html')

@main_bp.route('/bot/<int:bot_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_bot(bot_id):
    bot = Bot.query.get_or_404(bot_id)
    
    if bot.user_id != current_user.id and not current_user.is_admin:
        flash('Sizda bu botni tahrirlash huquqi yo\'q!', 'error')
        return redirect(url_for('main.dashboard'))
    
    if request.method == 'POST':
        bot.name = request.form.get('name', bot.name)
        bot.platform = request.form.get('platform', bot.platform)
        bot.telegram_token = request.form.get('telegram_token', bot.telegram_token)
        
        # Suhbat kuzatuvi sozlamalarini yangilash
        admin_chat_id = request.form.get('admin_chat_id')
        notification_channel = request.form.get('notification_channel')
        notifications_enabled = bool(request.form.get('notifications_enabled'))
        
        if admin_chat_id is not None:
            current_user.admin_chat_id = admin_chat_id.strip() if admin_chat_id.strip() else None
        if notification_channel is not None:
            current_user.notification_channel = notification_channel.strip() if notification_channel.strip() else None
        current_user.notifications_enabled = notifications_enabled
        
        # Agar Telegram bot token o'zgargan bo'lsa, qayta ishga tushirish (central manager)
        if bot.platform == 'Telegram' and bot.telegram_token:
            try:
                bot_manager.start_bot_polling(bot)
                bot.is_active = True
            except Exception as e:
                logging.error(f"Telegram botni ishga tushirishda xato: {e}")
                flash('Bot ma\'lumotlari yangilandi, lekin token noto\'g\'ri!', 'warning')
        
        db.session.commit()
        flash('Bot ma\'lumotlari yangilandi!', 'success')
        return redirect(url_for('main.dashboard'))
    
    return render_template('bot_edit.html', bot=bot)

@main_bp.route('/bot/<int:bot_id>/start', methods=['POST'])
@login_required
def start_bot(bot_id):
    """Botni qo'lbola ishga tushirish"""
    bot = Bot.query.get_or_404(bot_id)
    
    if bot.user_id != current_user.id and not current_user.is_admin:
        flash('Sizda bu botni ishga tushirish huquqi yo\'q!', 'error')
        return redirect(url_for('main.dashboard'))
    
    if bot.platform == 'Telegram' and bot.telegram_token:
        try:
            bot_manager.start_bot_polling(bot)
            bot.is_active = True
            db.session.commit()
            flash('Bot muvaffaqiyatli ishga tushirildi!', 'success')
        except Exception as e:
            flash(f'Xatolik: {str(e)}', 'error')
    else:
        flash('Bot tokenini tekshiring!', 'error')
    
    return redirect(url_for('main.dashboard'))

@main_bp.route('/bot/<int:bot_id>/stop', methods=['POST'])
@login_required
def stop_bot(bot_id):
    """Botni to'xtatish"""
    bot = Bot.query.get_or_404(bot_id)
    
    if bot.user_id != current_user.id and not current_user.is_admin:
        flash('Sizda bu botni to\'xtatish huquqi yo\'q!', 'error')
        return redirect(url_for('main.dashboard'))
    
    try:
        bot_manager.stop_bot_polling(bot.id, 'telegram')
        bot.is_active = False
        db.session.commit()
        flash('Bot to\'xtatildi!', 'success')
    except Exception as e:
        flash(f'Xatolik: {str(e)}', 'error')
    
    return redirect(url_for('main.dashboard'))

@main_bp.route('/bot/<int:bot_id>/knowledge', methods=['POST'])
@login_required
def upload_knowledge(bot_id):
    bot = Bot.query.get_or_404(bot_id)
    
    if bot.user_id != current_user.id and not current_user.is_admin:
        flash('Sizda bu botga ma\'lumot yuklash huquqi yo\'q!', 'error')
        return redirect(url_for('main.dashboard'))
    
    if 'file' not in request.files:
        flash('Fayl tanlanmagan!', 'error')
        return redirect(url_for('main.edit_bot', bot_id=bot_id))
    
    file = request.files['file']
    if file.filename == '':
        flash('Fayl tanlanmagan!', 'error')
        return redirect(url_for('main.edit_bot', bot_id=bot_id))
    
    if file:
        filename = secure_filename(file.filename or 'unknown')
        content = ""
        content_type = "file"
        
        try:
            # Check if it's an image file
            if filename.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp')):
                try:
                    import cloudinary
                    import cloudinary.uploader
                    from config import Config
                    
                    if not cloudinary.config().cloud_name:
                        cloudinary.config(
                            cloud_name=Config.CLOUDINARY_CLOUD_NAME,
                            api_key=Config.CLOUDINARY_API_KEY,
                            api_secret=Config.CLOUDINARY_API_SECRET
                        )
                        
                    upload_result = cloudinary.uploader.upload(
                        file,
                        folder=f"botfactory/kb_{bot_id}"
                    )
                    
                    # Store the secure URL returned by Cloudinary
                    content = upload_result.get('secure_url')
                    content_type = "image"
                except Exception as e:
                    logging.error(f"Cloudinary upload error in general KB: {e}")
                    raise Exception("Faylni Cloudinary xizmatiga yuklashda xatolik yuz berdi. API kalitlarni tekshiring.")
                
            elif filename.lower().endswith(('.xlsx', '.xls')):
                # Handle Excel files for bulk product import directly
                return handle_bulk_product_upload(file, bot_id)
                
            elif filename.endswith('.csv'):
                # Handle CSV files for knowledge base
                import pandas as pd
                try:
                    # Try reading CSV with UTF-8 encoding
                    file.seek(0)
                    df = pd.read_csv(file.stream, encoding='utf-8')
                except UnicodeDecodeError:
                    # Fallback to other encodings
                    file.seek(0)
                    try:
                        df = pd.read_csv(file.stream, encoding='cp1251')
                    except UnicodeDecodeError:
                        file.seek(0)
                        df = pd.read_csv(file.stream, encoding='latin-1')
                
                # Convert DataFrame to text content with clean formatting
                content = df.to_string(index=False)
                
                # Clean problematic Unicode characters
                unicode_replacements = {
                    '\u2019': "'", '\u2018': "'", '\u201c': '"', '\u201d': '"',
                    '\u2013': '-', '\u2014': '-', '\u2026': '...', '\u00a0': ' ',
                    '\u2010': '-', '\u2011': '-', '\u2012': '-', '\u2015': '-'
                }
                
                for unicode_char, replacement in unicode_replacements.items():
                    content = content.replace(unicode_char, replacement)
                    
                content_type = "file"
                
            elif filename.endswith('.txt'):
                # Handle different encodings for text files
                try:
                    content = file.read().decode('utf-8')
                except UnicodeDecodeError:
                    # Try with different encoding if UTF-8 fails
                    file.seek(0)
                    try:
                        content = file.read().decode('cp1251')  # Windows Cyrillic
                    except UnicodeDecodeError:
                        file.seek(0)
                        content = file.read().decode('latin-1', errors='ignore')
                
                # Clean problematic Unicode characters
                unicode_replacements = {
                    '\u2019': "'",  # Right single quotation mark
                    '\u2018': "'",  # Left single quotation mark
                    '\u201c': '"',  # Left double quotation mark
                    '\u201d': '"',  # Right double quotation mark
                    '\u2013': '-',  # En dash
                    '\u2014': '-',  # Em dash
                    '\u2026': '...',  # Horizontal ellipsis
                    '\u00a0': ' ',  # Non-breaking space
                    '\u2010': '-',  # Hyphen
                    '\u2011': '-',  # Non-breaking hyphen
                    '\u2012': '-',  # Figure dash
                    '\u2015': '-',  # Horizontal bar
                }
                
                for unicode_char, replacement in unicode_replacements.items():
                    content = content.replace(unicode_char, replacement)
                    
                content_type = "file"
                
            elif filename.endswith('.docx'):
                doc = docx.Document(file.stream)
                paragraphs = []
                for paragraph in doc.paragraphs:
                    # Clean Unicode characters from each paragraph
                    text = paragraph.text
                    unicode_replacements = {
                        '\u2019': "'", '\u2018': "'", '\u201c': '"', '\u201d': '"',
                        '\u2013': '-', '\u2014': '-', '\u2026': '...', '\u00a0': ' ',
                        '\u2010': '-', '\u2011': '-', '\u2012': '-', '\u2015': '-'
                    }
                    
                    for unicode_char, replacement in unicode_replacements.items():
                        text = text.replace(unicode_char, replacement)
                    paragraphs.append(text)
                content = '\n'.join(paragraphs)
            else:
                flash('Qo\'llab-quvvatlanadigan formatlar: .txt, .docx, .csv, .xlsx, .xls, .jpg, .png, .gif', 'error')
                return redirect(url_for('main.edit_bot', bot_id=bot_id))
            
            knowledge = KnowledgeBase()
            knowledge.bot_id = bot_id
            knowledge.content = content
            knowledge.filename = filename
            knowledge.content_type = content_type
            
            db.session.add(knowledge)
            db.session.commit()
            
            flash('Bilim bazasi muvaffaqiyatli yuklandi!', 'success')
        except Exception as e:
            # Safe error message handling to prevent encoding issues
            error_msg = 'Fayl yuklashda xatolik yuz berdi.'
            try:
                # Safely convert error to string, handling Unicode characters
                error_details = str(e)
                unicode_replacements = {
                    '\u2019': "'", '\u2018': "'", '\u201c': '"', '\u201d': '"',
                    '\u2013': '-', '\u2014': '-', '\u2026': '...', '\u00a0': ' ',
                    '\u2010': '-', '\u2011': '-', '\u2012': '-', '\u2015': '-'
                }
                
                for unicode_char, replacement in unicode_replacements.items():
                    error_details = error_details.replace(unicode_char, replacement)
                
                # Remove any remaining problematic Unicode characters
                error_details = error_details.encode('ascii', errors='ignore').decode('ascii')
                if error_details.strip():
                    error_msg = f'Fayl yuklashda xatolik: {error_details}'
            except:
                pass
            flash(error_msg, 'error')
    
    return redirect(url_for('main.edit_bot', bot_id=bot_id))

@main_bp.route('/bot/<int:bot_id>/knowledge/text', methods=['POST'])
@login_required
def add_text_knowledge(bot_id):
    bot = Bot.query.get_or_404(bot_id)
    
    if bot.user_id != current_user.id and not current_user.is_admin:
        flash('Sizda bu botga ma\'lumot qo\'shish huquqi yo\'q!', 'error')
        return redirect(url_for('main.dashboard'))
    
    content = request.form.get('content', '').strip()
    source_name = request.form.get('source_name', '').strip()
    
    if not content:
        flash('Matn maydoni bo\'sh bo\'lishi mumkin emas!', 'error')
        return redirect(url_for('main.edit_bot', bot_id=bot_id))
    
    if not source_name:
        source_name = f'Matn kirish - {datetime.utcnow().strftime("%d.%m.%Y %H:%M")}'
    
    try:
        # Clean problematic Unicode characters from user input
        unicode_replacements = {
            '\u2019': "'", '\u2018': "'", '\u201c': '"', '\u201d': '"',
            '\u2013': '-', '\u2014': '-', '\u2026': '...', '\u00a0': ' ',
            '\u2010': '-', '\u2011': '-', '\u2012': '-', '\u2015': '-'
        }
        
        for unicode_char, replacement in unicode_replacements.items():
            content = content.replace(unicode_char, replacement)
            source_name = source_name.replace(unicode_char, replacement)
        
        knowledge = KnowledgeBase()
        knowledge.bot_id = bot_id
        knowledge.content = content
        knowledge.content_type = 'text'
        knowledge.source_name = source_name
        
        db.session.add(knowledge)
        db.session.commit()
        
        flash('Matn muvaffaqiyatli qo\'shildi!', 'success')
    except Exception as e:
        error_msg = 'Matn qo\'shishda xatolik yuz berdi.'
        try:
            error_details = str(e)
            unicode_replacements = {
                '\u2019': "'", '\u2018': "'", '\u201c': '"', '\u201d': '"',
                '\u2013': '-', '\u2014': '-', '\u2026': '...', '\u00a0': ' ',
                '\u2010': '-', '\u2011': '-', '\u2012': '-', '\u2015': '-'
            }
            
            for unicode_char, replacement in unicode_replacements.items():
                error_details = error_details.replace(unicode_char, replacement)
            
            error_details = error_details.encode('ascii', errors='ignore').decode('ascii')
            if error_details.strip():
                error_msg = f'Matn qo\'shishda xatolik: {error_details}'
        except:
            pass
        flash(error_msg, 'error')
    return redirect(url_for('main.edit_bot', bot_id=bot_id))

@main_bp.route('/bot/<int:bot_id>/knowledge/<int:kb_id>/delete', methods=['DELETE'])
@login_required
def delete_knowledge(bot_id, kb_id):
    bot = Bot.query.get_or_404(bot_id)
    
    if bot.user_id != current_user.id and not current_user.is_admin:
        return jsonify({'success': False, 'error': "Huquq yo'q"}), 403
    
    knowledge = KnowledgeBase.query.filter_by(id=kb_id, bot_id=bot_id).first_or_404()
    
    try:
        db.session.delete(knowledge)
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@main_bp.route('/bot/<int:bot_id>/knowledge/<int:kb_id>/edit', methods=['POST'])
@login_required
def edit_knowledge(bot_id, kb_id):
    bot = Bot.query.get_or_404(bot_id)
    
    if bot.user_id != current_user.id and not current_user.is_admin:
        flash("Sizda axborotni o'zgartirish huquqi yo'q", 'error')
        return redirect(url_for('main.edit_bot', bot_id=bot_id))
        
    knowledge = KnowledgeBase.query.filter_by(id=kb_id, bot_id=bot_id).first_or_404()
    
    try:
        if knowledge.content_type == 'product':
            product_name = request.form.get('product_name', '').strip()
            product_price = request.form.get('product_price', '').strip()
            product_description = request.form.get('product_description', '').strip()
            
            if not product_name:
                flash("Mahsulot nomi kiritilishi shart!", 'error')
                return redirect(url_for('main.edit_bot', bot_id=bot_id))
                
            content_parts = [f"Mahsulot: {product_name}"]
            if product_price: content_parts.append(f"Narx: {product_price}")
            if product_description: content_parts.append(f"Tavsif: {product_description}")
            
            # Preserve existing image if any
            image_url_line = [line for line in knowledge.content.split('\\n') if line.startswith('Rasm:')]
            if image_url_line:
                content_parts.append(image_url_line[0])
                
            knowledge.source_name = product_name
            knowledge.content = "\\n".join(content_parts)
            
        elif knowledge.content_type == 'text':
            new_title = request.form.get('source_name', '').strip()
            new_content = request.form.get('content', '').strip()
            
            if not new_content:
                flash("Matn bo'sh bo'lishi mumkin emas", 'error')
                return redirect(url_for('main.edit_bot', bot_id=bot_id))
                
            knowledge.source_name = new_title or knowledge.source_name
            knowledge.content = new_content
            
        elif knowledge.content_type in ['file', 'image']:
            new_title = request.form.get('source_name', '').strip()
            if new_title:
                knowledge.source_name = new_title
                knowledge.filename = new_title # Overwrite display name
        
        db.session.commit()
        flash("Ma'lumot muvaffaqiyatli tahrirlandi!", 'success')
    except Exception as e:
        flash(f"Tahrirlashda xatolik: {str(e)}", 'error')
        
    return redirect(url_for('main.edit_bot', bot_id=bot_id))

@main_bp.route('/bot/<int:bot_id>/knowledge/image', methods=['POST'])
@login_required
def add_image_knowledge(bot_id):
    bot = Bot.query.get_or_404(bot_id)
    
    if bot.user_id != current_user.id and not current_user.is_admin:
        flash('Sizda bu botga rasm qo\'shish huquqi yo\'q!', 'error')
        return redirect(url_for('main.dashboard'))
    
    image_url = request.form.get('image_url', '').strip()
    source_name = request.form.get('source_name', '').strip()
    description = request.form.get('description', '').strip()
    
    if not image_url:
        flash('Rasm havolasi bo\'sh bo\'lishi mumkin emas!', 'error')
        return redirect(url_for('main.edit_bot', bot_id=bot_id))
    
    # Basic URL validation
    if not (image_url.startswith('http://') or image_url.startswith('https://')):
        flash('Yaroqli rasm havolasi kiriting (http:// yoki https:// bilan boshlanishi kerak)!', 'error')
        return redirect(url_for('main.edit_bot', bot_id=bot_id))
    
    if not source_name:
        source_name = f'Rasm havolasi - {datetime.utcnow().strftime("%d.%m.%Y %H:%M")}'
    
    # Combine image URL and description for content
    content = f"Rasm havolasi: {image_url}"
    if description:
        content += f"\nTavsif: {description}"
    
    try:
        knowledge = KnowledgeBase()
        knowledge.bot_id = bot_id
        knowledge.content = content
        knowledge.content_type = 'image_link'
        knowledge.source_name = source_name
        
        db.session.add(knowledge)
        db.session.commit()
        
        flash('Rasm havolasi muvaffaqiyatli qo\'shildi!', 'success')
    except Exception as e:
        flash('Rasm havolasini qo\'shishda xatolik yuz berdi.', 'error')
    
    return redirect(url_for('main.edit_bot', bot_id=bot_id))

@main_bp.route('/subscription')
@login_required
def subscription():
    return render_template('subscription.html')

@main_bp.route('/payment/<subscription_type>', methods=['POST'])
@login_required
def process_payment(subscription_type):
    method = request.form.get('method')
    
    amounts = {
        'starter': 165000,
        'basic': 290000,
        'premium': 590000
    }
    
    if subscription_type not in amounts:
        flash('Noto\'g\'ri tarif turi!', 'error')
        return redirect(url_for('main.subscription'))
    
    payment = Payment()
    payment.user_id = current_user.id
    payment.amount = amounts[subscription_type]
    payment.method = method
    payment.subscription_type = subscription_type
    payment.status = 'pending'
    
    db.session.add(payment)
    db.session.commit()
    
    # Here you would integrate with actual payment providers
    # For now, we'll simulate successful payment
    payment.status = 'completed'
    payment.transaction_id = f'TXN_{payment.id}_{datetime.utcnow().strftime("%Y%m%d%H%M%S")}'
    
    # Update user subscription
    current_user.subscription_type = subscription_type
    if subscription_type == 'starter':
        current_user.subscription_end_date = datetime.utcnow() + timedelta(days=30)
    elif subscription_type == 'basic':
        current_user.subscription_end_date = datetime.utcnow() + timedelta(days=30)
    elif subscription_type == 'premium':
        current_user.subscription_end_date = datetime.utcnow() + timedelta(days=30)
    
    db.session.commit()
    
    flash('To\'lov muvaffaqiyatli amalga oshirildi!', 'success')
    return redirect(url_for('main.dashboard'))

@main_bp.route('/api/dashboard/refresh')
@login_required
def dashboard_api():
    """API endpoint for dashboard data refresh"""
    bots = Bot.query.filter_by(user_id=current_user.id).all()
    active_bots = sum(1 for bot in bots if bot.is_active)
    
    return jsonify({
        'bot_count': len(bots),
        'active_bots': active_bots,
        'subscription_type': current_user.subscription_type,
        'subscription_active': current_user.subscription_active()
    })

@main_bp.route('/bot/<int:bot_id>/delete', methods=['POST'])
@login_required
def delete_bot(bot_id):
    bot = Bot.query.get_or_404(bot_id)
    
    if bot.user_id != current_user.id and not current_user.is_admin:
        flash('Sizda bu botni o\'chirish huquqi yo\'q!', 'error')
        return redirect(url_for('main.dashboard'))
    
    db.session.delete(bot)
    db.session.commit()
    
    flash('Bot muvaffaqiyatli o\'chirildi!', 'success')
    return redirect(url_for('main.dashboard'))
@main_bp.route('/bot/<int:bot_id>/knowledge/product', methods=['POST'])
@login_required
def add_product_knowledge(bot_id):
    """Mahsulot ma'lumotini qo'shish"""
    bot = Bot.query.get_or_404(bot_id)
    
    if bot.user_id != current_user.id and not current_user.is_admin:
        flash('Sizda bu botga mahsulot qo\'shish huquqi yo\'q!', 'error')
        return redirect(url_for('main.dashboard'))
    
    product_name = request.form.get('product_name', '').strip()
    product_price = request.form.get('product_price', '').strip()
    product_description = request.form.get('product_description', '').strip()
    product_image_url = request.form.get('product_image_url', '').strip()
    product_image_file = request.files.get('product_image_file')

    # Cloudinary ga rasmni yuklash
    if product_image_file and product_image_file.filename != '':
        try:
            import cloudinary
            import cloudinary.uploader
            from config import Config
            
            if not cloudinary.config().cloud_name:
                cloudinary.config(
                    cloud_name=Config.CLOUDINARY_CLOUD_NAME,
                    api_key=Config.CLOUDINARY_API_KEY,
                    api_secret=Config.CLOUDINARY_API_SECRET
                )
                
            upload_result = cloudinary.uploader.upload(
                product_image_file,
                folder=f"botfactory/product_{bot_id}"
            )
            product_image_url = upload_result.get('secure_url')
        except Exception as e:
            logging.error(f"Cloudinary upload error in product addition: {e}")
            flash('Rasmni yuklashda xatolik yuz berdi (Cloudinary API sozlamasini tekshiring).', 'error')
            return redirect(url_for('main.edit_bot', bot_id=bot_id))
    
    if not product_name:
        flash('Mahsulot nomi kiritilishi shart!', 'error')
        return redirect(url_for('main.edit_bot', bot_id=bot_id))
    
    # Mahsulot ma'lumotlarini birlashtirish
    content_parts = [f"Mahsulot: {product_name}"]
    
    if product_price:
        content_parts.append(f"Narx: {product_price}")
    
    if product_description:
        content_parts.append(f"Tavsif: {product_description}")
    
    if product_image_url:
        content_parts.append(f"Rasm: {product_image_url}")
    
    content = "\n".join(content_parts)
    
    try:
        knowledge = KnowledgeBase()
        knowledge.bot_id = bot_id
        knowledge.content = content
        knowledge.filename = None
        knowledge.content_type = 'product'
        knowledge.source_name = product_name
        
        db.session.add(knowledge)
        db.session.commit()
        
        # Debug: log mahsulot qo'shilishini
        logging.info(f"DEBUG: New product added - Name: {product_name}, Bot ID: {bot_id}, Content: {content[:100]}...")
        
        flash(f'"{product_name}" mahsuloti muvaffaqiyatli qo\'shildi!', 'success')
    except Exception as e:
        logging.error(f"DEBUG: Product creation failed: {str(e)}")
        flash('Mahsulot qo\'shishda xatolik yuz berdi!', 'error')
    
    return redirect(url_for('main.edit_bot', bot_id=bot_id))

# Bulk import functions moved to top of file

@main_bp.route('/bot/<int:bot_id>/knowledge/bulk-products', methods=['POST'])
@login_required
def upload_bulk_products(bot_id):
    """Excel/CSV orqali ko'p mahsulot qo'shish"""
    bot = Bot.query.get_or_404(bot_id)
    
    if bot.user_id != current_user.id and not current_user.is_admin:
        flash('Sizda bu botga mahsulot qo\'shish huquqi yo\'q!', 'error')
        return redirect(url_for('main.dashboard'))
    
    if 'bulk_file' not in request.files:
        flash('Fayl tanlanmadi!', 'error')
        return redirect(url_for('main.edit_bot', bot_id=bot_id))
    
    file = request.files['bulk_file']
    if file.filename == '':
        flash('Fayl tanlanmadi!', 'error')
        return redirect(url_for('main.edit_bot', bot_id=bot_id))
    
    # Fayl format tekshirish
    allowed_extensions = {'.xlsx', '.xls', '.csv'}
    filename = file.filename or ''
    file_ext = os.path.splitext(filename)[1].lower()
    if file_ext not in allowed_extensions:
        flash('Faqat Excel yoki CSV fayllar qabul qilinadi!', 'error')
        return redirect(url_for('main.edit_bot', bot_id=bot_id))
    
    try:
        # Fayl stream'ini pandas'ga o'qish
        if file_ext == '.csv':
            df = pd.read_csv(file.stream)
        else:
            df = pd.read_excel(file.stream)
        
        # Ustunlar nomini standartlashtirish
        expected_columns = ['mahsulot_nomi', 'narx', 'tavsif', 'rasm_url']
        if len(df.columns) >= 1:
            # Birinchi 4 ta ustunni standart nomlarga o'zgartirish
            new_columns = {}
            for i, col in enumerate(df.columns[:4]):
                if i < len(expected_columns):
                    new_columns[col] = expected_columns[i]
            df.rename(columns=new_columns, inplace=True)
        
        # Bo'sh qatorlarni olib tashlash
        df = df.dropna(subset=['mahsulot_nomi'])
        
        added_count = 0
        errors = []
        
        for idx, row in df.iterrows():
            row_num = int(idx) + 2  # Excel qator raqami
            try:
                product_name = str(row.get('mahsulot_nomi', '')).strip()
                if not product_name or product_name == 'nan':
                    continue
                
                product_price = str(row.get('narx', '')).strip()
                if product_price == 'nan':
                    product_price = ''
                
                product_description = str(row.get('tavsif', '')).strip()
                if product_description == 'nan':
                    product_description = ''
                
                product_image_url = str(row.get('rasm_url', '')).strip()
                if product_image_url == 'nan':
                    product_image_url = ''
                
                # Mahsulot ma'lumotlarini birlashtirish
                content_parts = [f"Mahsulot: {product_name}"]
                
                if product_price:
                    content_parts.append(f"Narx: {product_price}")
                
                if product_description:
                    content_parts.append(f"Tavsif: {product_description}")
                
                if product_image_url:
                    content_parts.append(f"Rasm: {product_image_url}")
                
                content = '\n'.join(content_parts)
                
                # Ma'lumotlar bazasiga qo'shish
                knowledge = KnowledgeBase()
                knowledge.bot_id = bot_id
                knowledge.content = content
                knowledge.filename = None
                knowledge.content_type = 'product'
                knowledge.source_name = product_name
                
                db.session.add(knowledge)
                added_count += 1
                
            except Exception as e:
                errors.append(f'Qator {row_num}: {str(e)}')
        
        db.session.commit()
        
        if added_count > 0:
            flash(f'{added_count} ta mahsulot muvaffaqiyatli qo\'shildi!', 'success')
        
        if errors:
            flash(f'Ba\'zi qatorlarda xatoliklar: {len(errors)} ta xatolik', 'warning')
            
    except Exception as e:
        flash(f'Fayl o\'qishda xatolik: {str(e)}', 'error')
    
    return redirect(url_for('main.edit_bot', bot_id=bot_id))

@main_bp.route('/template/products.xlsx')
def download_template():
    """Excel namuna fayl yuklash"""
    # Namuna ma'lumotlar
    sample_data = {
        'mahsulot_nomi': ['Kartoshka', 'Piyoz', 'Sabzi', 'Pomidor', 'Olcha'],
        'narx': ['2500 som/kg', '3000 som/kg', '4000 som/kg', '5000 som/kg', '8000 som/kg'],
        'tavsif': [
            'Yangi hosil kartoshka, yuqori sifat, minimal 100kg',
            'Quruq piyoz, saqlash muddati uzoq, minimal 50kg', 
            'Toza sabzi, organik o\'stirilgan, minimal 20kg',
            'Qizil pomidor, yangi terilgan, minimal 30kg',
            'Shirin olcha, organik, minimal 10kg'
        ],
        'rasm_url': [
            'https://example.com/kartoshka.jpg',
            'https://example.com/piyoz.jpg', 
            'https://example.com/sabzi.jpg',
            'https://example.com/pomidor.jpg',
            'https://example.com/olcha.jpg'
        ]
    }
    
    df = pd.DataFrame(sample_data)
    
    # Excel faylni xotirada yaratish
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Mahsulotlar', index=False)
        
        # Ustunlar kengligini sozlash
        worksheet = writer.sheets['Mahsulotlar']
        worksheet.column_dimensions['A'].width = 20  # Mahsulot nomi
        worksheet.column_dimensions['B'].width = 15  # Narx
        worksheet.column_dimensions['C'].width = 40  # Tavsif
        worksheet.column_dimensions['D'].width = 30  # Rasm URL
    
    output.seek(0)
    
    return send_file(
        output,
        as_attachment=True,
        download_name='mahsulotlar_namuna.xlsx',
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )

@main_bp.route('/webhook/telegram/<int:bot_id>', methods=['POST'])
def telegram_webhook(bot_id):
    """Telegram webhook endpoint for production"""
    try:
        webhook_secret = (os.environ.get('TELEGRAM_WEBHOOK_SECRET') or '').strip()
        if webhook_secret:
            provided_secret = (request.headers.get('X-Telegram-Bot-Api-Secret-Token') or '').strip()
            if provided_secret != webhook_secret:
                return jsonify({'error': 'Invalid webhook secret'}), 403

        client_ip = get_client_ip(request)
        allowed, retry_after = rate_limiter.is_allowed(
            key=f"telegram_webhook:{bot_id}:{client_ip}",
            limit=240,
            window_seconds=60
        )
        if not allowed:
            return jsonify({'error': 'Rate limited', 'retry_after': retry_after}), 429

        # Bot mavjudligini tekshirish
        bot = Bot.query.get_or_404(bot_id)
        
        # Webhook ma'lumotlarini olish
        update_data = request.get_json()
        
        if not update_data:
            return jsonify({'error': 'No data received'}), 400
            
        # Telegram bot instance yaratish va update ni qayta ishlash
        from telegram_bot import process_webhook_update
        result = process_webhook_update(bot_id, bot.telegram_token, update_data)
        
        if result:
            return jsonify({'status': 'ok'}), 200
        else:
            return jsonify({'error': 'Processing failed'}), 500
            
    except Exception as e:
        logging.error(f"Webhook error for bot {bot_id}: {str(e)}")
        return jsonify({'error': 'Internal error'}), 500

@main_bp.route('/bot/<int:bot_id>/setup_webhook', methods=['POST'])
@login_required
def setup_webhook(bot_id):
    """Webhook ni o'rnatish"""
    try:
        bot = Bot.query.get_or_404(bot_id)
        
        # Foydalanuvchi huquqini tekshirish
        if bot.user_id != current_user.id and not current_user.is_admin:
            flash('Sizda bu botga ruxsat yo\'q!', 'error')
            return redirect(url_for('main.dashboard'))
            
        if not bot.telegram_token:
            flash('Avval Telegram token ni kiriting!', 'error')
            return redirect(url_for('main.edit_bot', bot_id=bot_id))
            
        # Domain ni aniqlash
        webhook_url = get_webhook_url(bot_id)
        
        # Telegram API orqali webhook o'rnatish
        success = set_telegram_webhook(bot.telegram_token, webhook_url)
        
        if success:
            flash('✅ Webhook muvaffaqiyatli o\'rnatildi!', 'success')
            bot.is_active = True
            db.session.commit()
        else:
            flash('❌ Webhook o\'rnatishda xatolik yuz berdi!', 'error')
            
    except Exception as e:
        flash(f'Xatolik: {str(e)}', 'error')
        
    return redirect(url_for('main.edit_bot', bot_id=bot_id))

def get_webhook_url(bot_id):
    """Webhook URL ni aniqlash"""
    # Production muhitni aniqlash
    if os.environ.get('RENDER') or 'render' in request.headers.get('Host', '').lower():
        # Render.com muhiti - to'g'ri service name
        return f"https://chatbotfactory.onrender.com/webhook/telegram/{bot_id}"
    elif request.headers.get('Host'):
        # Boshqa hosting xizmatlari uchun
        host = request.headers.get('Host')
        scheme = 'https' if request.headers.get('X-Forwarded-Proto') == 'https' else 'http'
        return f"{scheme}://{host}/webhook/telegram/{bot_id}"
    else:
        # Fallback - Render URL
        return f"https://chatbotfactory.onrender.com/webhook/telegram/{bot_id}"

def set_telegram_webhook(bot_token, webhook_url):
    """Telegram API orqali webhook o'rnatish"""
    try:
        api_url = f"https://api.telegram.org/bot{bot_token}/setWebhook"
        payload = {
            'url': webhook_url,
            'max_connections': 40,
            'allowed_updates': ['message', 'callback_query']
        }
        
        response = requests.post(api_url, json=payload)
        result = response.json()
        
        if result.get('ok'):
            logging.info(f"Webhook set successfully: {webhook_url}")
            return True
        else:
            logging.error(f"Webhook setup failed: {result.get('description', 'Unknown error')}")
            return False
            
    except Exception as e:
        logging.error(f"Webhook setup error: {str(e)}")
        return False

# === Bot Messaging Routes ===

@main_bp.route('/bot/<int:bot_id>/messaging')
@login_required
def bot_messaging(bot_id):
    """Bot mijozlari va xabar yuborish interfeysi"""
    bot = Bot.query.get_or_404(bot_id)
    
    if bot.user_id != current_user.id and not current_user.is_admin:
        flash('Sizda bu botning xabarlariga kirish huquqi yo\'q!', 'error')
        return redirect(url_for('main.dashboard'))
    
    # Bot mijozlarini olish
    customers = BotCustomer.query.filter_by(bot_id=bot_id, is_active=True).order_by(BotCustomer.last_interaction.desc()).all()
    
    # Xabar tarixi
    recent_messages = BotMessage.query.filter_by(bot_id=bot_id).order_by(BotMessage.created_at.desc()).limit(10).all()
    
    return render_template('bot_messaging.html', bot=bot, customers=customers, recent_messages=recent_messages)

@main_bp.route('/bot/<int:bot_id>/send_message', methods=['POST'])
@login_required
def send_bot_message(bot_id):
    """Bot orqali mijozlarga xabar yuborish"""
    bot = Bot.query.get_or_404(bot_id)
    
    if bot.user_id != current_user.id and not current_user.is_admin:
        flash('Sizda bu bot orqali xabar yuborish huquqi yo\'q!', 'error')
        return redirect(url_for('main.dashboard'))
    
    message_text = request.form.get('message_text', '').strip()
    message_type = request.form.get('message_type', 'individual')  # individual/broadcast
    selected_customers = request.form.getlist('selected_customers')
    
    if not message_text:
        flash('Xabar matni kiritilishi shart!', 'error')
        return redirect(url_for('main.bot_messaging', bot_id=bot_id))
    
    # Xabar ob'ektini yaratish
    bot_message = BotMessage()
    bot_message.bot_id = bot_id
    bot_message.sender_id = current_user.id
    bot_message.message_text = message_text
    bot_message.message_type = message_type
    
    if message_type == 'broadcast':
        # Barcha faol mijozlarga yuborish
        target_customers = BotCustomer.query.filter_by(bot_id=bot_id, is_active=True).all()
    else:
        # Tanlangan mijozlarga yuborish
        if not selected_customers:
            flash('Kamida bitta mijoz tanlanishi kerak!', 'error')
            return redirect(url_for('main.bot_messaging', bot_id=bot_id))
        target_customers = BotCustomer.query.filter(
            BotCustomer.id.in_(selected_customers),
            BotCustomer.bot_id == bot_id
        ).all()
    
    import json
    bot_message.target_customers = json.dumps([str(c.id) for c in target_customers])
    bot_message.status = 'sending'
    
    db.session.add(bot_message)
    db.session.commit()
    
    # Xabarlarni yuborish (asinxron)
    try:
        success_count = 0
        for customer in target_customers:
            try:
                platform = (customer.platform or '').lower()
                target_id = str(customer.platform_user_id or '').strip()
                if not target_id:
                    continue
                if platform == 'telegram' and bot.telegram_token:
                    result = send_telegram_message_sync(bot.telegram_token, target_id, message_text)
                    if result:
                        success_count += 1
                elif platform == 'whatsapp' and bot.whatsapp_token and bot.whatsapp_phone_id:
                    try:
                        from whatsapp_bot import WhatsAppBot
                        wa = WhatsAppBot(bot.whatsapp_token, bot.whatsapp_phone_id, bot.id)
                        if wa.send_message(target_id, message_text):
                            success_count += 1
                    except Exception as e:
                        logging.error(f"WhatsApp send error for customer {customer.id}: {e}")
                elif platform == 'instagram' and bot.instagram_token:
                    try:
                        from instagram_bot import InstagramBot
                        ig = InstagramBot(bot.instagram_token, bot.id)
                        if ig.send_message(target_id, message_text):
                            success_count += 1
                    except Exception as e:
                        logging.error(f"Instagram send error for customer {customer.id}: {e}")
                else:
                    logging.warning(f"Unsupported or misconfigured platform for customer {customer.id}: {platform}")
            except Exception as e:
                logging.error(f"Error sending message to customer {customer.id}: {str(e)}")
        
        # Natijalarni yangilash
        bot_message.sent_count = success_count
        bot_message.status = 'completed' if success_count > 0 else 'failed'
        bot_message.sent_at = datetime.utcnow()
        db.session.commit()
        
        if success_count > 0:
            flash(f'Xabar {success_count} ta mijozga muvaffaqiyatli yuborildi!', 'success')
        else:
            flash('Xabar yuborishda muammo yuz berdi!', 'error')
            
    except Exception as e:
        logging.error(f"Message sending error: {str(e)}")
        bot_message.status = 'failed'
        db.session.commit()
        flash('Xabar yuborishda xatolik yuz berdi!', 'error')
    
    return redirect(url_for('main.bot_messaging', bot_id=bot_id))

@main_bp.route('/bot/<int:bot_id>/customers')
@login_required
def bot_customers(bot_id):
    """Bot mijozlar ro'yxati (JSON format)"""
    bot = Bot.query.get_or_404(bot_id)
    
    if bot.user_id != current_user.id and not current_user.is_admin:
        return jsonify({'error': 'Access denied'}), 403
    
    customers = BotCustomer.query.filter_by(bot_id=bot_id, is_active=True).all()
    
    customer_data = []
    for customer in customers:
        customer_data.append({
            'id': customer.id,
            'display_name': customer.display_name,
            'platform': customer.platform,
            'language': customer.language,
            'last_interaction': customer.last_interaction.strftime('%Y-%m-%d %H:%M'),
            'message_count': customer.message_count
        })
    
    return jsonify({'customers': customer_data})

def send_telegram_message_sync(bot_token, chat_id, message_text):
    """Telegram xabarini sinxron yuborish"""
    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        data = {
            'chat_id': chat_id,
            'text': message_text,
            'parse_mode': 'HTML'
        }
        
        response = requests.post(url, json=data, timeout=30)
        result = response.json()
        
        return result.get('ok', False)
    except Exception as e:
        logging.error(f"Error sending telegram message: {str(e)}")
        return False
