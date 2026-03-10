"""Knowledge base routes"""
import os
import logging
from datetime import datetime
from io import BytesIO
from flask import Blueprint, request, redirect, url_for, flash, jsonify, send_file
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from app import db
from models import Bot, KnowledgeBase
import docx
import pandas as pd

knowledge_bp = Blueprint('knowledge', __name__)


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
            row_num = int(idx) + 2
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
                
                content_parts = [f"Mahsulot: {product_name}"]
                if product_price:
                    content_parts.append(f"Narx: {product_price}")
                if product_description:
                    content_parts.append(f"Tavsif: {product_description}")
                if product_image_url:
                    content_parts.append(f"Rasm: {product_image_url}")
                
                content = "\n".join(content_parts)
                
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
        
        db.session.commit()
        
        if added_count > 0:
            flash(f'{added_count} ta mahsulot muvaffaqiyatli qo\'shildi!', 'success')
        if errors:
            error_text = '; '.join(errors[:5])
            flash(f'Ba\'zi qatorlarda xatoliklar: {error_text}', 'warning')
        
    except Exception as e:
        flash(f'Excel/CSV fayl qayta ishlashda xatolik: {str(e)}', 'error')
    
    return redirect(url_for('bot.edit_bot', bot_id=bot_id))


@knowledge_bp.route('/bot/<int:bot_id>/knowledge', methods=['POST'])
@login_required
def upload_knowledge(bot_id):
    bot = Bot.query.get_or_404(bot_id)
    
    if bot.user_id != current_user.id and not current_user.is_admin:
        flash('Sizda bu botga ma\'lumot yuklash huquqi yo\'q!', 'error')
        return redirect(url_for('main.dashboard'))
    
    if 'file' not in request.files:
        flash('Fayl tanlanmagan!', 'error')
        return redirect(url_for('bot.edit_bot', bot_id=bot_id))
    
    file = request.files['file']
    if file.filename == '':
        flash('Fayl tanlanmagan!', 'error')
        return redirect(url_for('bot.edit_bot', bot_id=bot_id))
    
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
                    
                    content = upload_result.get('secure_url')
                    content_type = "image"
                except Exception as e:
                    logging.error(f"Cloudinary upload error in general KB: {e}")
                    raise Exception("Faylni Cloudinary xizmatiga yuklashda xatolik yuz berdi. API kalitlarni tekshiring.")
                
            elif filename.lower().endswith(('.xlsx', '.xls')):
                return handle_bulk_product_upload(file, bot_id)
                
            elif filename.endswith('.csv'):
                try:
                    file.seek(0)
                    df = pd.read_csv(file.stream, encoding='utf-8')
                except UnicodeDecodeError:
                    file.seek(0)
                    try:
                        df = pd.read_csv(file.stream, encoding='cp1251')
                    except UnicodeDecodeError:
                        file.seek(0)
                        df = pd.read_csv(file.stream, encoding='latin-1')
                
                content = df.to_string(index=False)
                
                unicode_replacements = {
                    '\u2019': "'", '\u2018': "'", '\u201c': '"', '\u201d': '"',
                    '\u2013': '-', '\u2014': '-', '\u2026': '...', '\u00a0': ' ',
                    '\u2010': '-', '\u2011': '-', '\u2012': '-', '\u2015': '-'
                }
                
                for unicode_char, replacement in unicode_replacements.items():
                    content = content.replace(unicode_char, replacement)
                    
                content_type = "file"
                
            elif filename.endswith('.txt'):
                try:
                    content = file.read().decode('utf-8')
                except UnicodeDecodeError:
                    file.seek(0)
                    try:
                        content = file.read().decode('cp1251')
                    except UnicodeDecodeError:
                        file.seek(0)
                        content = file.read().decode('latin-1', errors='ignore')
                
                unicode_replacements = {
                    '\u2019': "'", '\u2018': "'", '\u201c': '"', '\u201d': '"',
                    '\u2013': '-', '\u2014': '-', '\u2026': '...', '\u00a0': ' ',
                    '\u2010': '-', '\u2011': '-', '\u2012': '-', '\u2015': '-'
                }
                
                for unicode_char, replacement in unicode_replacements.items():
                    content = content.replace(unicode_char, replacement)
                    
                content_type = "file"
                
            elif filename.endswith('.docx'):
                doc = docx.Document(file.stream)
                paragraphs = []
                for paragraph in doc.paragraphs:
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
                return redirect(url_for('bot.edit_bot', bot_id=bot_id))
            
            knowledge = KnowledgeBase()
            knowledge.bot_id = bot_id
            knowledge.content = content
            knowledge.filename = filename
            knowledge.content_type = content_type
            
            db.session.add(knowledge)
            db.session.commit()
            
            flash('Bilim bazasi muvaffaqiyatli yuklandi!', 'success')
        except Exception as e:
            error_msg = 'Fayl yuklashda xatolik yuz berdi.'
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
                    error_msg = f'Fayl yuklashda xatolik: {error_details}'
            except Exception:
                pass
            flash(error_msg, 'error')
    
    return redirect(url_for('bot.edit_bot', bot_id=bot_id))


@knowledge_bp.route('/bot/<int:bot_id>/knowledge/text', methods=['POST'])
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
        return redirect(url_for('bot.edit_bot', bot_id=bot_id))
    
    if not source_name:
        source_name = f'Matn kirish - {datetime.utcnow().strftime("%d.%m.%Y %H:%M")}'
    
    try:
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
    return redirect(url_for('bot.edit_bot', bot_id=bot_id))


@knowledge_bp.route('/bot/<int:bot_id>/knowledge/<int:kb_id>/delete', methods=['DELETE'])
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


@knowledge_bp.route('/bot/<int:bot_id>/knowledge/<int:kb_id>/edit', methods=['POST'])
@login_required
def edit_knowledge(bot_id, kb_id):
    bot = Bot.query.get_or_404(bot_id)
    
    if bot.user_id != current_user.id and not current_user.is_admin:
        flash("Sizda axborotni o'zgartirish huquqi yo'q", 'error')
        return redirect(url_for('bot.edit_bot', bot_id=bot_id))
        
    knowledge = KnowledgeBase.query.filter_by(id=kb_id, bot_id=bot_id).first_or_404()
    
    try:
        if knowledge.content_type == 'product':
            product_name = request.form.get('product_name', '').strip()
            product_price = request.form.get('product_price', '').strip()
            product_description = request.form.get('product_description', '').strip()
            
            if not product_name:
                flash("Mahsulot nomi kiritilishi shart!", 'error')
                return redirect(url_for('bot.edit_bot', bot_id=bot_id))
                
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
                return redirect(url_for('bot.edit_bot', bot_id=bot_id))
                
            knowledge.source_name = new_title or knowledge.source_name
            knowledge.content = new_content
            
        elif knowledge.content_type in ['file', 'image']:
            new_title = request.form.get('source_name', '').strip()
            if new_title:
                knowledge.source_name = new_title
                knowledge.filename = new_title
        
        db.session.commit()
        flash("Ma'lumot muvaffaqiyatli tahrirlandi!", 'success')
    except Exception as e:
        flash(f"Tahrirlashda xatolik: {str(e)}", 'error')
        
    return redirect(url_for('bot.edit_bot', bot_id=bot_id))


@knowledge_bp.route('/bot/<int:bot_id>/knowledge/image', methods=['POST'])
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
        return redirect(url_for('bot.edit_bot', bot_id=bot_id))
    
    if not (image_url.startswith('http://') or image_url.startswith('https://')):
        flash('Yaroqli rasm havolasi kiriting (http:// yoki https:// bilan boshlanishi kerak)!', 'error')
        return redirect(url_for('bot.edit_bot', bot_id=bot_id))
    
    if not source_name:
        source_name = f'Rasm havolasi - {datetime.utcnow().strftime("%d.%m.%Y %H:%M")}'
    
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
    
    return redirect(url_for('bot.edit_bot', bot_id=bot_id))


@knowledge_bp.route('/bot/<int:bot_id>/knowledge/product', methods=['POST'])
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
            return redirect(url_for('bot.edit_bot', bot_id=bot_id))
    
    if not product_name:
        flash('Mahsulot nomi kiritilishi shart!', 'error')
        return redirect(url_for('bot.edit_bot', bot_id=bot_id))
    
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
        
        logging.info(f"DEBUG: New product added - Name: {product_name}, Bot ID: {bot_id}, Content: {content[:100]}...")
        
        flash(f'"{product_name}" mahsuloti muvaffaqiyatli qo\'shildi!', 'success')
    except Exception as e:
        logging.error(f"DEBUG: Product creation failed: {str(e)}")
        flash('Mahsulot qo\'shishda xatolik yuz berdi!', 'error')
    
    return redirect(url_for('bot.edit_bot', bot_id=bot_id))


@knowledge_bp.route('/bot/<int:bot_id>/knowledge/bulk-products', methods=['POST'])
@login_required
def upload_bulk_products(bot_id):
    """Excel/CSV orqali ko'p mahsulot qo'shish"""
    bot = Bot.query.get_or_404(bot_id)
    
    if bot.user_id != current_user.id and not current_user.is_admin:
        flash('Sizda bu botga mahsulot qo\'shish huquqi yo\'q!', 'error')
        return redirect(url_for('main.dashboard'))
    
    if 'bulk_file' not in request.files:
        flash('Fayl tanlanmadi!', 'error')
        return redirect(url_for('bot.edit_bot', bot_id=bot_id))
    
    file = request.files['bulk_file']
    if file.filename == '':
        flash('Fayl tanlanmadi!', 'error')
        return redirect(url_for('bot.edit_bot', bot_id=bot_id))
    
    allowed_extensions = {'.xlsx', '.xls', '.csv'}
    filename = file.filename or ''
    file_ext = os.path.splitext(filename)[1].lower()
    if file_ext not in allowed_extensions:
        flash('Faqat Excel yoki CSV fayllar qabul qilinadi!', 'error')
        return redirect(url_for('bot.edit_bot', bot_id=bot_id))
    
    try:
        if file_ext == '.csv':
            df = pd.read_csv(file.stream)
        else:
            df = pd.read_excel(file.stream)
        
        expected_columns = ['mahsulot_nomi', 'narx', 'tavsif', 'rasm_url']
        if len(df.columns) >= 1:
            new_columns = {}
            for i, col in enumerate(df.columns[:4]):
                if i < len(expected_columns):
                    new_columns[col] = expected_columns[i]
            df.rename(columns=new_columns, inplace=True)
        
        df = df.dropna(subset=['mahsulot_nomi'])
        
        added_count = 0
        errors = []
        
        for idx, row in df.iterrows():
            row_num = int(idx) + 2
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
                
                content_parts = [f"Mahsulot: {product_name}"]
                
                if product_price:
                    content_parts.append(f"Narx: {product_price}")
                
                if product_description:
                    content_parts.append(f"Tavsif: {product_description}")
                
                if product_image_url:
                    content_parts.append(f"Rasm: {product_image_url}")
                
                content = '\n'.join(content_parts)
                
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
    
    return redirect(url_for('bot.edit_bot', bot_id=bot_id))


@knowledge_bp.route('/template/products.xlsx')
def download_template():
    """Excel namuna fayl yuklash"""
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
    
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Mahsulotlar', index=False)
        
        worksheet = writer.sheets['Mahsulotlar']
        worksheet.column_dimensions['A'].width = 20
        worksheet.column_dimensions['B'].width = 15
        worksheet.column_dimensions['C'].width = 40
        worksheet.column_dimensions['D'].width = 30
    
    output.seek(0)
    
    return send_file(
        output,
        as_attachment=True,
        download_name='mahsulotlar_namuna.xlsx',
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )


@knowledge_bp.route('/download-sample-excel')
@login_required  
def download_sample_excel():
    """Namuna Excel faylini yuklab olish"""
    try:
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
        
        df = pd.DataFrame(sample_data)
        
        output = BytesIO()
        
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
