import os
import asyncio
import logging
from pathlib import Path
from typing import Optional, Dict
import threading
import queue

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Updater,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    Filters,
    CallbackContext,
)
import yt_dlp

# ========== KONFIGURASI ==========
TOKEN = os.environ.get("BOT_TOKEN", "")
OWNER_ID = int(os.environ.get("OWNER_ID", "0"))

if not TOKEN:
    raise ValueError("BOT_TOKEN not set!")

# Path download
DOWNLOAD_DIR = Path("/tmp/hirako_downloads")
DOWNLOAD_DIR.mkdir(exist_ok=True)

# Queue untuk komunikasi antar thread
download_queue = queue.Queue()

# Logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ========== FUNGSI DETEKSI PLATFORM ==========
def detect_platform(url: str) -> str:
    url_lower = url.lower()
    if 'youtube.com' in url_lower or 'youtu.be' in url_lower:
        return 'youtube'
    elif 'tiktok.com' in url_lower or 'vt.tiktok.com' in url_lower:
        return 'tiktok'
    elif 'instagram.com' in url_lower:
        return 'instagram'
    elif 'twitter.com' in url_lower or 'x.com' in url_lower:
        return 'twitter'
    elif 'facebook.com' in url_lower or 'fb.watch' in url_lower:
        return 'facebook'
    elif 'spotify.com' in url_lower:
        return 'spotify'
    else:
        return 'unknown'

# ========== FUNGSI DOWNLOAD ==========
def download_video_sync(url: str, platform: str) -> Optional[Path]:
    """Download video secara synchronous (untuk dijalankan di thread)"""
    output_template = str(DOWNLOAD_DIR / f"%(title)s_%(id)s.%(ext)s")
    
    ydl_opts = {
        'format': 'best[filesize<45M]',
        'outtmpl': output_template,
        'quiet': True,
        'no_warnings': True,
        'ignoreerrors': True,
    }
    
    # Khusus YouTube batasi 480p
    if platform == 'youtube':
        ydl_opts['format'] = 'best[height<=480][filesize<45M]/best[filesize<45M]'
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if info:
                filename = ydl.prepare_filename(info)
                # Cek file exist
                if Path(filename).exists():
                    return Path(filename)
                
                # Coba cari file dengan ekstensi berbeda
                for ext in ['.mp4', '.webm', '.mkv']:
                    test_path = Path(str(filename).rsplit('.', 1)[0] + ext)
                    if test_path.exists():
                        return test_path
        return None
    except Exception as e:
        logger.error(f"Download error {platform}: {e}")
        return None

def download_worker():
    """Worker thread untuk memproses download"""
    while True:
        try:
            # Ambil task dari queue
            task = download_queue.get(timeout=1)
            if task is None:
                break
            
            chat_id = task['chat_id']
            url = task['url']
            platform = task['platform']
            status_msg_id = task['status_msg_id']
            context = task['context']
            
            # Lakukan download
            file_path = download_video_sync(url, platform)
            
            # Kirim hasil
            if file_path and file_path.exists():
                # Kirim video
                try:
                    with open(file_path, 'rb') as video:
                        context.bot.send_video(
                            chat_id=chat_id,
                            video=video,
                            caption=f"✅ *Download Berhasil!*\n"
                                   f"📌 Platform: {platform.upper()}\n"
                                   f"📦 Ukuran: {file_path.stat().st_size / (1024*1024):.1f} MB\n"
                                   f"🤖 @{context.bot.get_me().username}",
                            parse_mode='Markdown',
                            timeout=60
                        )
                    
                    # Hapus status message
                    context.bot.delete_message(chat_id=chat_id, message_id=status_msg_id)
                    
                except Exception as e:
                    logger.error(f"Send video error: {e}")
                    context.bot.send_message(
                        chat_id=chat_id,
                        text=f"⚠️ Gagal mengirim video: {str(e)[:100]}",
                        parse_mode='Markdown'
                    )
                
                # Hapus file
                try:
                    file_path.unlink()
                except:
                    pass
            else:
                # Gagal download
                context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=status_msg_id,
                    text=f"❌ *Gagal Download!*\n\n"
                         f"Platform: {platform.upper()}\n"
                         f"Penyebab:\n"
                         f"• Video terlalu besar (>45MB)\n"
                         f"• Link private/expired\n"
                         f"• Server sedang sibuk\n\n"
                         f"Coba link lain ya!",
                    parse_mode='Markdown'
                )
                
        except queue.Empty:
            continue
        except Exception as e:
            logger.error(f"Worker error: {e}")

# ========== HANDLER ==========
def start(update: Update, context: CallbackContext):
    """Handler /start - Menu utama"""
    keyboard = [
        [InlineKeyboardButton("📥 CARA DOWNLOAD", callback_data='help')],
        [InlineKeyboardButton("🎵 SPOTIFY", callback_data='spotify'),
         InlineKeyboardButton("📸 INSTAGRAM", callback_data='instagram')],
        [InlineKeyboardButton("▶️ YOUTUBE", callback_data='youtube'),
         InlineKeyboardButton("🎵 TIKTOK", callback_data='tiktok')],
        [InlineKeyboardButton("🐦 TWITTER", callback_data='twitter'),
         InlineKeyboardButton("👥 FACEBOOK", callback_data='facebook')],
        [InlineKeyboardButton("⭐ DONASI", callback_data='donasi'),
         InlineKeyboardButton("👤 OWNER", url=f"tg://user?id={OWNER_ID}")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    update.message.reply_text(
        f"✨ *HIRAKO BOT* ✨\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🤖 *All-in-One Downloader*\n\n"
        f"Halo *{update.effective_user.first_name}*!\n\n"
        f"✅ *Support:*\n"
        f"▶️ YouTube | 🎵 TikTok | 📸 Instagram\n"
        f"🐦 Twitter | 👥 Facebook | 🎵 Spotify\n\n"
        f"📤 *Kirim link*, saya download!",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

def help_command(update: Update, context: CallbackContext):
    update.message.reply_text(
        f"📖 *PANDUAN HIRAKO BOT*\n\n"
        f"1️⃣ *Copy link* dari aplikasi\n"
        f"2️⃣ *Paste link* di chat ini\n"
        f"3️⃣ *Tunggu* 5-15 detik\n"
        f"4️⃣ *Video terkirim* otomatis!\n\n"
        f"⚠️ *BATASAN:*\n"
        f"• File max 45MB\n"
        f"• YouTube 480p\n\n"
        f"💡 Link harus *public*!",
        parse_mode='Markdown'
    )

def donasi_command(update: Update, context: CallbackContext):
    update.message.reply_text(
        f"❤️ *DUKUNG HIRAKO BOT* ❤️\n\n"
        f"Bot ini *GRATIS*!\n\n"
        f"💰 *Saweria:* [saweria.co/hirako](https://saweria.co/hirako)\n\n"
        f"Terima kasih! 🙏",
        parse_mode='Markdown',
        disable_web_page_preview=True
    )

def handle_url(update: Update, context: CallbackContext):
    """Handler untuk link yang dikirim"""
    url = update.message.text.strip()
    platform = detect_platform(url)
    
    if platform == 'unknown':
        update.message.reply_text(
            f"❌ *Link tidak dikenali*\n\n"
            f"Kirim link dari:\n"
            f"YouTube | TikTok | Instagram | Twitter | Facebook | Spotify",
            parse_mode='Markdown'
        )
        return
    
    # Emoji platform
    emoji_map = {
        'youtube': '▶️', 'tiktok': '🎵', 'instagram': '📸',
        'twitter': '🐦', 'facebook': '👥', 'spotify': '🎵'
    }
    emoji = emoji_map.get(platform, '📹')
    
    # Kirim pesan status
    status_msg = update.message.reply_text(
        f"{emoji} *Mendownload dari {platform.upper()}...*\n"
        f"⏳ Mohon tunggu sebentar...\n\n"
        f"_Proses download bisa 10-30 detik_",
        parse_mode='Markdown'
    )
    
    # Masukkan ke queue untuk diproses worker
    task = {
        'chat_id': update.effective_chat.id,
        'url': url,
        'platform': platform,
        'status_msg_id': status_msg.message_id,
        'context': context
    }
    download_queue.put(task)
    
    logger.info(f"Task added to queue: {platform} - {url[:50]}")

def button_callback(update: Update, context: CallbackContext):
    """Handler untuk button inline"""
    query = update.callback_query
    query.answer()
    
    if query.data == 'help':
        query.edit_message_text(
            f"📖 *CARA PAKAI HIRAKO BOT*\n\n"
            f"1. Buka YouTube/TikTok/IG\n"
            f"2. Share → Copy Link\n"
            f"3. Paste link di chat bot\n"
            f"4. Tunggu video masuk!\n\n"
            f"🎯 *Mudah kan?*",
            parse_mode='Markdown'
        )
    elif query.data == 'spotify':
        query.edit_message_text(
            f"🎵 *DOWNLOAD SPOTIFY*\n\n"
            f"1. Buka lagu di Spotify\n"
            f"2. Share → Copy Link\n"
            f"3. Paste link di chat\n"
            f"4. Tunggu convert ke MP3\n\n"
            f"⏱️ Butuh 10-30 detik",
            parse_mode='Markdown'
        )
    elif query.data == 'donasi':
        query.edit_message_text(
            f"❤️ *SUPPORT HIRAKO BOT* ❤️\n\n"
            f"💰 Saweria: [saweria.co/hirako](https://saweria.co/hirako)\n\n"
            f"Terima kasih! 🙏",
            parse_mode='Markdown',
            disable_web_page_preview=True
        )
    elif query.data in ['youtube', 'tiktok', 'instagram', 'twitter', 'facebook']:
        query.edit_message_text(
            f"✅ *{query.data.upper()} READY*\n\n"
            f"Kirim link video {query.data.upper()} langsung ke chat!",
            parse_mode='Markdown'
        )

def error_handler(update: Update, context: CallbackContext):
    """Handler error global"""
    logger.error(f"Update {update} caused error {context.error}")
    if update and update.effective_message:
        update.effective_message.reply_text(
            "⚠️ Terjadi kesalahan, coba lagi ya!"
        )

# ========== MAIN ==========
def main():
    """Start the bot"""
    # Buat folder download
    DOWNLOAD_DIR.mkdir(exist_ok=True)
    
    # Start worker thread untuk download
    worker_thread = threading.Thread(target=download_worker, daemon=True)
    worker_thread.start()
    
    # Buat updater dengan version python-telegram-bot 13.x
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher
    
    # Command handlers
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("help", help_command))
    dp.add_handler(CommandHandler("donasi", donasi_command))
    
    # Message handler untuk URL
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_url))
    
    # Callback query handler untuk button
    dp.add_handler(CallbackQueryHandler(button_callback))
    
    # Error handler
    dp.add_error_handler(error_handler)
    
    # Start bot
    logger.info("🚀 HIRAKO BOT STARTED! 🚀")
    logger.info(f"Bot: @{updater.bot.get_me().username}")
    logger.info(f"Download dir: {DOWNLOAD_DIR}")
    
    # Start polling
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
