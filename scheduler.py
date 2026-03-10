import os
import logging
import time
import threading
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta

try:
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger
    from apscheduler.triggers.interval import IntervalTrigger
    from apscheduler.executors.pool import ThreadPoolExecutor
    from apscheduler.jobstores.memory import MemoryJobStore
    APSCHEDULER_AVAILABLE = True
except ImportError:
    # Fallback to simple schedule library
    import schedule
    APSCHEDULER_AVAILABLE = False
    logging.warning("APScheduler not available, using simple schedule library")

from app import db, app
from models import User, Payment, Bot, ChatHistory
from marketing import MarketingCampaigns
from utils import check_subscription_expiry, get_user_stats, get_payment_stats

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TaskScheduler:
    """Professional background vazifalar boshqaruvchisi APScheduler bilan"""
    
    def __init__(self):
        self.campaigns = MarketingCampaigns()
        self.running = False
        self.scheduler = None
        
        if APSCHEDULER_AVAILABLE:
            # APScheduler konfiguratsiyasi
            jobstores = {'default': MemoryJobStore()}
            executors = {'default': ThreadPoolExecutor(20)}
            job_defaults = {
                'coalesce': False,
                'max_instances': 3,
                'misfire_grace_time': 30
            }
            self.scheduler = BackgroundScheduler(
                jobstores=jobstores,
                executors=executors,
                job_defaults=job_defaults,
                timezone='Asia/Tashkent'
            )
        else:
            # Fallback scheduler
            self.scheduler_thread = None
    
    def start(self) -> bool:
        """Scheduler ni ishga tushirish"""
        if not self.running:
            try:
                self.running = True
                self.setup_jobs()
                
                if APSCHEDULER_AVAILABLE and self.scheduler:
                    self.scheduler.start()
                    logger.info("APScheduler started successfully")
                else:
                    # Fallback to simple scheduler
                    self.scheduler_thread = threading.Thread(target=self.run_fallback_scheduler)
                    self.scheduler_thread.daemon = True
                    self.scheduler_thread.start()
                    logger.info("Fallback scheduler started")
                
                return True
            except Exception as e:
                logger.error(f"Failed to start scheduler: {str(e)}")
                return False
        return True
    
    def stop(self) -> bool:
        """Scheduler ni to'xtatish"""
        try:
            self.running = False
            
            if APSCHEDULER_AVAILABLE and self.scheduler:
                self.scheduler.shutdown(wait=True)
                logger.info("APScheduler stopped successfully")
            else:
                # Fallback scheduler
                if self.scheduler_thread:
                    self.scheduler_thread.join()
                logger.info("Fallback scheduler stopped")
            
            return True
        except Exception as e:
            logger.error(f"Failed to stop scheduler: {str(e)}")
            return False
    
    def setup_jobs(self) -> None:
        """Professional vazifalarni sozlash"""
        try:
            if APSCHEDULER_AVAILABLE and self.scheduler:
                # APScheduler bilan professional joblar
                
                # Har kuni soat 9:00 da obunalarni tekshirish  
                self.scheduler.add_job(
                    func=self.check_subscriptions,
                    trigger=CronTrigger(hour=9, minute=0, timezone='Asia/Tashkent'),
                    id='check_subscriptions',
                    name='Daily subscription check',
                    replace_existing=True
                )
                
                # Har kuni soat 10:00 da eslatmalar yuborish
                self.scheduler.add_job(
                    func=self.send_reminders,
                    trigger=CronTrigger(hour=10, minute=0, timezone='Asia/Tashkent'),
                    id='send_reminders',
                    name='Daily reminders',
                    replace_existing=True
                )
                
                # Haftada ikki marta bepul foydalanuvchilarga marketing (Dushanba va Payshanba 14:00)
                self.scheduler.add_job(
                    func=self.send_marketing_campaigns,
                    trigger=CronTrigger(day_of_week='mon,thu', hour=14, minute=0, timezone='Asia/Tashkent'),
                    id='marketing_campaigns',
                    name='Twice weekly marketing campaigns',
                    replace_existing=True
                )
                
                # Har kuni yarim tungi ma'lumotlarni tozalash
                self.scheduler.add_job(
                    func=self.cleanup_old_data,
                    trigger=CronTrigger(hour=0, minute=0, timezone='Asia/Tashkent'),
                    id='cleanup_data',
                    name='Daily data cleanup',
                    replace_existing=True
                )
                
                # Har soat bot statistikalarini yangilash
                self.scheduler.add_job(
                    func=self.update_bot_stats,
                    trigger=IntervalTrigger(hours=1),
                    id='update_stats',
                    name='Hourly stats update',
                    replace_existing=True
                )
                
                # Har 15 daqiqada tizim holatini tekshirish
                self.scheduler.add_job(
                    func=self.system_health_check,
                    trigger=IntervalTrigger(minutes=15),
                    id='health_check',
                    name='System health check',
                    replace_existing=True
                )
                
                # Har 5 daqiqada muddati tugash arafasidagi foydalanuvchilarga ogohlantirish
                self.scheduler.add_job(
                    func=self.send_expiry_warnings,
                    trigger=IntervalTrigger(minutes=5),
                    id='expiry_warnings',
                    name='Subscription expiry warnings',
                    replace_existing=True
                )
                
                logger.info("APScheduler jobs configured successfully")
                
            else:
                # Fallback simple scheduler
                import schedule
                schedule.every().day.at("09:00").do(self.check_subscriptions)
                schedule.every().day.at("10:00").do(self.send_reminders)
                schedule.every().monday.at("14:00").do(self.send_marketing_campaigns)
                schedule.every().thursday.at("14:00").do(self.send_marketing_campaigns)
                schedule.every().day.at("00:00").do(self.cleanup_old_data)
                schedule.every().hour.do(self.update_bot_stats)
                schedule.every(15).minutes.do(self.system_health_check)
                logger.info("Fallback scheduler jobs configured")
                
        except Exception as e:
            logger.error(f"Failed to setup jobs: {str(e)}")
    
    def run_fallback_scheduler(self) -> None:
        """Fallback scheduler ishga tushirish"""
        import schedule
        while self.running:
            try:
                schedule.run_pending()
                time.sleep(1)
            except Exception as e:
                logger.error(f"Fallback scheduler error: {str(e)}")
                time.sleep(60)  # Xato bo'lsa 1 daqiqa kutish
    
    def check_subscriptions(self) -> None:
        """Obunalarni tekshirish"""
        try:
            logger.info("Checking subscriptions...")
            
            with app.app_context():
                # 3 kun qolgan obunalar (starter/basic/premium)
                three_days_later = datetime.utcnow() + timedelta(days=3)
                expiring_soon = User.query.filter(
                    User.subscription_end_date <= three_days_later,
                    User.subscription_end_date > datetime.utcnow(),
                    User.subscription_type.in_(['starter', 'basic', 'premium'])
                ).all()
                
                reminder_count = 0
                for user in expiring_soon:
                    days_left = (user.subscription_end_date - datetime.utcnow()).days
                    try:
                        # Email eslatma yuborish
                        email_success = self.campaigns.send_subscription_reminder(user, days_left)
                        
                        # Telegram orqali ham eslatma yuborish (agar admin chat ID mavjud bo'lsa)
                        telegram_success = False
                        if user.admin_chat_id:
                            from notification_service import TelegramNotificationService
                            telegram_service = TelegramNotificationService()
                            
                            user_info = {
                                'username': user.username,
                                'subscription_type': user.subscription_type,
                                'subscription_end_date': user.subscription_end_date.strftime('%d.%m.%Y') if user.subscription_end_date else 'Noma\'lum'
                            }
                            
                            telegram_success = telegram_service.send_subscription_reminder(
                                user.admin_chat_id, user_info, days_left
                            )
                        
                        if email_success or telegram_success:
                            reminder_count += 1
                    except Exception as e:
                        logger.error(f"Reminder send error for user {user.id}: {str(e)}")

                # 3 kun qolgan BEPUL ta'riflar uchun eslatma
                free_expiring_soon = User.query.filter(
                    User.subscription_end_date <= three_days_later,
                    User.subscription_end_date > datetime.utcnow(),
                    User.subscription_type == 'free'
                ).all()
                
                free_reminder_count = 0
                for user in free_expiring_soon:
                    days_left = (user.subscription_end_date - datetime.utcnow()).days
                    try:
                        # Email va SMS eslatma yuborish
                        email_success = self.campaigns.send_subscription_reminder(user, days_left)
                        sms_success = self.campaigns.send_trial_ending_sms(user, days_left)
                        
                        # Telegram orqali ham eslatma (agar admin chat ID mavjud bo'lsa)
                        telegram_success = False
                        if user.admin_chat_id:
                            from notification_service import TelegramNotificationService
                            telegram_service = TelegramNotificationService()
                            
                            user_info = {
                                'username': user.username,
                                'subscription_type': user.subscription_type,
                                'subscription_end_date': user.subscription_end_date.strftime('%d.%m.%Y') if user.subscription_end_date else 'Noma\'lum'
                            }
                            
                            telegram_success = telegram_service.send_subscription_reminder(
                                user.admin_chat_id, user_info, days_left
                            )
                        
                        if email_success or sms_success or telegram_success:
                            free_reminder_count += 1
                    except Exception as e:
                        logger.error(f"Free trial reminder error for user {user.id}: {str(e)}")
                
                # Tugagan obunalar
                expired_users = User.query.filter(
                    User.subscription_end_date <= datetime.utcnow(),
                    User.subscription_type.in_(['starter', 'basic', 'premium'])
                ).all()
                
                expired_count = 0
                for user in expired_users:
                    try:
                        old_subscription_type = user.subscription_type
                        user.subscription_type = 'free'
                        user.subscription_end_date = None
                        
                        # Botlarni deaktivatsiya qilish
                        for bot in user.bots:
                            if bot.platform != 'Telegram':  # Faqat Telegram bepul uchun
                                bot.is_active = False
                        
                        db.session.commit()
                        expired_count += 1
                        
                        # Telegram orqali tugash xabari yuborish
                        if user.admin_chat_id:
                            try:
                                from notification_service import TelegramNotificationService
                                telegram_service = TelegramNotificationService()
                                
                                user_info = {
                                    'username': user.username,
                                    'old_subscription_type': old_subscription_type
                                }
                                
                                telegram_service.send_subscription_expired_notification(
                                    user.admin_chat_id, user_info
                                )
                            except Exception as tg_error:
                                logger.error(f"Telegram expiry notification error for user {user.id}: {str(tg_error)}")
                        
                        logger.info(f"Subscription expired for user {user.id}")
                        
                    except Exception as e:
                        logger.error(f"Expiry processing error for user {user.id}: {str(e)}")
                        db.session.rollback()
                
                # Tugagan BEPUL ta'riflar uchun xabar
                expired_free_users = User.query.filter(
                    User.subscription_end_date <= datetime.utcnow(),
                    User.subscription_type == 'free'
                ).all()
                
                expired_free_count = 0
                for user in expired_free_users:
                    try:
                        # Tugagan kun xabari
                        self.campaigns.send_subscription_expired_notification(user)
                        
                        # Obunani bekor qilish
                        user.subscription_end_date = None
                        db.session.commit()
                        expired_free_count += 1
                        
                    except Exception as e:
                        logger.error(f"Free expiry processing error for user {user.id}: {str(e)}")
                        db.session.rollback()
                
                logger.info(f"Subscription check completed: {reminder_count} paid reminders, {free_reminder_count} free reminders, {expired_count} paid expired, {expired_free_count} free expired")
                
        except Exception as e:
            logger.error(f"Check subscriptions error: {str(e)}")
    
    def send_reminders(self) -> None:
        """Eslatmalar yuborish"""
        try:
            logger.info("Sending reminders...")
            
            with app.app_context():
                # 1 kun qolgan bepul sinov
                tomorrow = datetime.utcnow() + timedelta(days=1)
                trial_ending = User.query.filter(
                    User.subscription_type == 'free',
                    User.subscription_end_date <= tomorrow,
                    User.subscription_end_date > datetime.utcnow()
                ).all()
                
                trial_count = 0
                for user in trial_ending:
                    try:
                        # Email va SMS yuborish
                        email_success = self.campaigns.send_subscription_reminder(user, 1)
                        sms_success = self.campaigns.send_trial_ending_sms(user, 1)
                        
                        if email_success or sms_success:
                            trial_count += 1
                            
                    except Exception as e:
                        logger.error(f"Trial reminder error for user {user.id}: {str(e)}")
                
                logger.info(f"Reminders sent: {trial_count} trial ending")
                
        except Exception as e:
            logger.error(f"Send reminders error: {str(e)}")
    
    def send_marketing_campaigns(self) -> None:
        """Marketing kampaniyalari yuborish"""
        try:
            logger.info("Sending marketing campaigns...")
            
            with app.app_context():
                # 7 kundan ortiq bepul foydalanuvchilar
                week_ago = datetime.utcnow() - timedelta(days=7)
                free_users = User.query.filter(
                    User.subscription_type == 'free',
                    User.created_at <= week_ago,
                    User.is_active.is_(True)
                ).all()
                
                marketing_count = 0
                for user in free_users:
                    try:
                        success = self.campaigns.send_free_user_marketing(user)
                        if success:
                            marketing_count += 1
                            
                        # Har 10 ta xabardan keyin 1 soniya kutish (spam oldini olish)
                        if marketing_count % 10 == 0:
                            time.sleep(1)
                            
                    except Exception as e:
                        logger.error(f"Marketing send error for user {user.id}: {str(e)}")
                
                logger.info(f"Marketing campaigns sent: {marketing_count}")
                
        except Exception as e:
            logger.error(f"Marketing campaigns error: {str(e)}")
    
    def cleanup_old_data(self) -> None:
        """Eski ma'lumotlarni tozalash"""
        try:
            logger.info("Cleaning up old data...")
            
            with app.app_context():
                # 90 kundan eski chat tarixi
                ninety_days_ago = datetime.utcnow() - timedelta(days=90)
                old_chats = ChatHistory.query.filter(
                    ChatHistory.created_at < ninety_days_ago
                ).delete()
                
                # Bekor qilingan to'lovlar (30 kundan eski)
                thirty_days_ago = datetime.utcnow() - timedelta(days=30)
                old_failed_payments = Payment.query.filter(
                    Payment.status == 'failed',
                    Payment.created_at < thirty_days_ago
                ).delete()
                
                # O'chirilgan foydalanuvchilarning ma'lumotlari
                inactive_users = User.query.filter(
                    User.is_active.is_(False),
                    User.created_at < thirty_days_ago
                ).count()
                
                db.session.commit()
                
                logger.info(f"Cleanup completed: {old_chats} old chats, {old_failed_payments} failed payments")
                
        except Exception as e:
            logger.error(f"Cleanup error: {str(e)}")
            db.session.rollback()
    
    def update_bot_stats(self) -> None:
        """Bot statistikalarini yangilash"""
        try:
            logger.info("Updating bot statistics...")
            
            with app.app_context():
                # Har bir bot uchun statistika
                bots = Bot.query.filter_by(is_active=True).all()
                
                for bot in bots:
                    try:
                        # So'nggi 24 soatdagi xabarlar soni
                        yesterday = datetime.utcnow() - timedelta(days=1)
                        daily_messages = ChatHistory.query.filter(
                            ChatHistory.bot_id == bot.id,
                            ChatHistory.created_at >= yesterday
                        ).count()
                        
                        # Haftalik statistika
                        week_ago = datetime.utcnow() - timedelta(days=7)
                        weekly_messages = ChatHistory.query.filter(
                            ChatHistory.bot_id == bot.id,
                            ChatHistory.created_at >= week_ago
                        ).count()
                        
                        # Bot ma'lumotlarini yangilash (qo'shimcha maydonlar kerak)
                        # bot.daily_messages = daily_messages
                        # bot.weekly_messages = weekly_messages
                        # bot.last_updated = datetime.utcnow()
                        
                    except Exception as e:
                        logger.error(f"Bot {bot.id} stats error: {str(e)}")
                
                db.session.commit()
                logger.info(f"Bot statistics updated for {len(bots)} bots")
                
        except Exception as e:
            logger.error(f"Update bot stats error: {str(e)}")
    
    def system_health_check(self) -> None:
        """Tizim salomatligini tekshirish"""
        try:
            with app.app_context():
                # Database ulanishini tekshirish
                user_count = User.query.count()
                
                # Aktiv botlar soni
                active_bots = Bot.query.filter_by(is_active=True).count()
                
                # So'nggi 1 soatdagi xabarlar
                hour_ago = datetime.utcnow() - timedelta(hours=1)
                recent_messages = ChatHistory.query.filter(
                    ChatHistory.created_at >= hour_ago
                ).count()
                
                # Disk bo'sh joyi (Linux uchun)
                import shutil
                total, used, free = shutil.disk_usage("/")
                disk_free_gb = free // (1024**3)
                
                # Ogohlantirishlar
                if disk_free_gb < 1:  # 1GB dan kam
                    logger.warning(f"Low disk space: {disk_free_gb}GB free")
                
                # Haftalik hisobot (yakshanba kuni)
                if datetime.utcnow().weekday() == 6:  # Sunday
                    self.send_weekly_report()
                
                logger.debug(f"Health check: {user_count} users, {active_bots} bots, {recent_messages} messages/hour")
                
        except Exception as e:
            logger.error(f"System health check error: {str(e)}")
    
    def send_weekly_report(self):
        """Haftalik hisobot yuborish"""
        try:
            logger.info("Sending weekly report...")
            
            with app.app_context():
                # Admin foydalanuvchilarni topish
                admins = User.query.filter_by(is_admin=True).all()
                
                # Statistikalar
                user_stats = get_user_stats()
                payment_stats = get_payment_stats()
                
                week_ago = datetime.utcnow() - timedelta(days=7)
                weekly_stats = {
                    'new_users': User.query.filter(User.created_at >= week_ago).count(),
                    'new_bots': Bot.query.filter(Bot.created_at >= week_ago).count(),
                    'messages_sent': ChatHistory.query.filter(ChatHistory.created_at >= week_ago).count(),
                    'payments_completed': Payment.query.filter(
                        Payment.status == 'completed',
                        Payment.created_at >= week_ago
                    ).count()
                }
                
                # Hisobot emaili
                subject = f"📊 Chatbot Factory AI - Haftalik hisobot ({datetime.utcnow().strftime('%d.%m.%Y')})"
                
                report_html = f"""
                <h2>📊 Haftalik hisobot</h2>
                <p>Sana: {datetime.utcnow().strftime('%d.%m.%Y')}</p>
                
                <h3>👥 Foydalanuvchilar</h3>
                <ul>
                    <li>Jami: {user_stats['total_users']}</li>
                    <li>Yangi (hafta): {weekly_stats['new_users']}</li>
                    <li>Bepul: {user_stats['free_users']}</li>
                    <li>Basic: {user_stats['basic_users']}</li>
                    <li>Premium: {user_stats['premium_users']}</li>
                </ul>
                
                <h3>🤖 Botlar</h3>
                <ul>
                    <li>Jami botlar: {weekly_stats['new_bots']}</li>
                    <li>Yangi botlar (hafta): {weekly_stats['new_bots']}</li>
                    <li>Yuborilgan xabarlar: {weekly_stats['messages_sent']}</li>
                </ul>
                
                <h3>💰 To'lovlar</h3>
                <ul>
                    <li>Haftalik to'lovlar: {weekly_stats['payments_completed']}</li>
                    <li>Umumiy daromad: {payment_stats['total_revenue']:,.0f} so'm</li>
                    <li>Oylik daromad: {payment_stats['monthly_revenue']:,.0f} so'm</li>
                </ul>
                """
                
                for admin in admins:
                    try:
                        self.campaigns.email_service.send_email(
                            admin.email,
                            subject,
                            report_html
                        )
                    except Exception as e:
                        logger.error(f"Weekly report send error for {admin.email}: {str(e)}")
                
                logger.info(f"Weekly report sent to {len(admins)} admins")
                
        except Exception as e:
            logger.error(f"Weekly report error: {str(e)}")

# Global scheduler instance
scheduler = TaskScheduler()

# Scheduler management functions
def start_scheduler():
    """Scheduler ni ishga tushirish"""
    scheduler.start()

def stop_scheduler():
    """Scheduler ni to'xtatish"""
    scheduler.stop()

# Manual task execution functions (admin panel uchun)
def run_subscription_check():
    """Qo'lda obunalarni tekshirish"""
    scheduler.check_subscriptions()

def run_marketing_campaign():
    """Qo'lda marketing kampaniyasi"""
    scheduler.send_marketing_campaigns()

def run_cleanup():
    """Qo'lda tozalash"""
    scheduler.cleanup_old_data()

# Scheduler ni avtomatik ishga tushirish (app.py da chaqiriladi)
if __name__ == "__main__":
    start_scheduler()
    
    # Keep running
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Shutting down scheduler...")
        stop_scheduler()