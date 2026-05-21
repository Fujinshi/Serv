import os
import asyncio
import logging
from pathlib import Path
from typing import Optional
import re
import subprocess

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
import requests
from bs4 import BeautifulSoup

# ========== KONFIGURASI ==========
TOKEN = os.environ.get("BOT_TOKEN", "")
OWNER_ID = int(os.environ.get("OWNER_ID", "0"))

if not TOKEN:
    raise ValueError("BOT_TOKEN not set!")

# Path download
DOWNLOAD_DIR = Path("/tmp/hirako_downloads")
DOWNLOAD_DIR.mkdir(exist_ok=True)

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
    elif 'tiktok.com' in url_lower:
        return 'tiktok'
    elif 'instagram.com' in url_lower:
        return 'instagram'
    elif 'twitter.com' in url_lower or 'x.com' in url_lower:
        return 'twitter'
    elif 'facebook.com' in url_lower or 'fb.watch' in url_lower:
        return 'facebook'
    elif 'spotify.com' in url_lower:
        return 'spotify'
    elif 'pinterest.com' in url_lower:
        return 'pinterest'
    else:
        return 'unknown'

# ========== FUNGSI DOWNLOAD ==========
async def download_youtube(url: str) -> Optional[Path]:
    """Download YouTube video (max 480p)"""
    output = DOWNLOAD_DIR / '%(title)s_%(id)s.%(ext)s'
    ydl_opts = {
        'format': 'best[height<=480][filesize<45M]/best[filesize<45M]',
        'outtmpl': str(output),
        'quiet': True,
        'no_warnings': True,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            if Path(filename).exists():
                return Path(filename)
        return None
    except Exception as e:
        logger.error(f"YouTube error: {e}")
        return None

async def download_tiktok(url: str) -> Optional[Path]:
    """Download TikTok video (no watermark)"""
    output = DOWNLOAD_DIR / '%(title)s_%(id)s.%(ext)s'
    ydl_opts = {
        'format': 'best',
        'outtmpl': str(output),
        'quiet': True,
        'no_warnings': True,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            if Path(filename).exists():
                return Path(filename)
        return None
    except Exception as e:
        logger.error(f"TikTok error: {e}")
        return None

async def download_instagram(url: str) -> Optional[Path]:
    """Download Instagram video/reel"""
    output = DOWNLOAD_DIR / '%(title)s_%(id)s.%(ext)s'
    ydl_opts = {
        'format': 'best',
        'outtmpl': str(output),
        'quiet': True,
        'no_warnings': True,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            if Path(filename).exists():
                return Path(filename)
        return None
    except Exception as e:
        logger.error(f"Instagram error: {e}")
        return None

async def download_spotify(track_url: str) -> Optional[Path]:
    """Download Spotify track using spotdl"""
    output = DOWNLOAD_DIR / '{artist} - {title}.mp3'
    try:
        cmd = [
            'spotdl', track_url,
            '--output', str(output),
            '--format', 'mp3'
        ]
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await process.communicate()
        
        # Cari file mp3 yang terdownload
        for file in DOWNLOAD_DIR.glob('*.mp3'):
            if file.stat().st_size > 0:
                return file
        return None
    except Exception as e:
        logger.error(f"Spotify error: {e}")
        return None

async def download_general(url: str) -> Optional[Path]:
    """Download from other platforms"""
    output = DOWNLOAD_DIR / '%(title)s_%(id)s.%(ext)s'
    ydl_opts = {
        'format': 'best[filesize<45M]',
        'outtmpl': str(output),
        'quiet': True,
        'no_warnings': True,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            if Path(filename).exists():
                return Path(filename)
        return None
    except Exception as e:
        logger.error(f"General error: {e}")
        return None

# ========== HANDLER ==========
def start(update: Update, context: CallbackContext):
    """Handler /start - Menu utama KECE"""
    keyboard = [
        [InlineKeyboardButton("📥 CARA DOWNLOAD", callback_data='help')],
        [InlineKeyboardButton("🎵 SPOTIFY", callback_data='spotify'),
         InlineKeyboardButton("📸 INSTAGRAM", callback_data='instagram')],
        [InlineKeyboardButton("▶️ YOUTUBE", callback_data='youtube'),
         InlineKeyboardButton("🎵 TIKTOK", callback_data='tiktok')],
        [InlineKeyboardButton("🐦 TWITTER", callback_data='twitter'),
         InlineKeyboardButton("👥 FACEBOOK", callback_data='facebook')],
        [InlineKeyboardButton("⭐ SUPPORT", callback_data='donasi'),
         InlineKeyboardButton("👤 OWNER", url=f"tg://user?id={OWNER_ID}")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    update.message.reply_text(
        f"✨ *HIRAKO BOT* ✨\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🤖 *Premium Downloader All Sosmed*\n\n"
        f"Halo *{update.effective_user.first_name}*!\n\n"
        f"✅ *Supported Platform:*\n"
        f"▶️ YouTube | 🎵 TikTok | 📸 Instagram\n"
        f"🐦 Twitter | 👥 Facebook | 🎵 Spotify\n"
        f"📌 Pinterest | Dan lainnya\n\n"
        f"📤 *Cara Pakai:*\n"
        f"Kirimkan link video/musik, saya akan download!\n\n"
        f"_⚡ Fast | 🎯 Mudah | 🔒 Aman_",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

def help_command(update: Update, context: CallbackContext):
    update.message.reply_text(
        f"📖 *PANDUAN HIRAKO BOT*\n\n"
        f"1️⃣ *Copy link* dari aplikasi:\n"
        f"   • YouTube: Share → Copy link\n"
        f"   • TikTok: Share → Copy link\n"
        f"   • Spotify: Share → Copy link\n\n"
        f"2️⃣ *Paste link* di chat ini\n\n"
        f"3️⃣ *Tunggu* 5-15 detik\n\n"
        f"4️⃣ *Video/Musik* akan terkirim!\n\n"
        f"⚠️ *BATASAN:*\n"
        f"• File max 45MB (kebijakan Telegram)\n"
        f"• YouTube dibatasi 480p\n"
        f"• Spotify butuh waktu lebih lama\n\n"
        f"💡 *Tips:* Gunakan link *public* ya!",
        parse_mode='Markdown'
    )

def donasi_command(update: Update, context: CallbackContext):
    update.message.reply_text(
        f"❤️ *DUKUNG HIRAKO BOT* ❤️\n\n"
        f"Bot ini *GRATIS* selamanya!\n"
        f"Tapi kalau mau donasi:\n\n"
        f"💰 *Saweria:* [klik disini](https://saweria.co/hirako)\n"
        f"💎 *Dana:* 08123456789\n\n"
        f"Makasih banyak yang sudah pakai Hirako Bot! 🙏\n"
        f"_Donasi membuat bot ini tetap hidup_",
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
            f"✓ YouTube\n✓ TikTok\n✓ Instagram\n"
            f"✓ Twitter\n✓ Facebook\n✓ Spotify\n\n"
            f"Atau ketik /help untuk bantuan",
            parse_mode='Markdown'
        )
        return
    
    # Emoji dan pesan platform
    platform_names = {
        'youtube': ('YouTube', '▶️'),
        'tiktok': ('TikTok', '🎵'),
        'instagram': ('Instagram', '📸'),
        'twitter': ('Twitter', '🐦'),
        'facebook': ('Facebook', '👥'),
        'spotify': ('Spotify', '🎵'),
        'pinterest': ('Pinterest', '📌'),
    }
    name, emoji = platform_names.get(platform, (platform.upper(), '📹'))
    
    # Notifikasi
    status_msg = update.message.reply_text(
        f"{emoji} *Mendownload dari {name}...*\n"
        f"⏳ Mohon tunggu, sedang diproses...\n\n"
        f"_File akan terkirim otomatis_",
        parse_mode='Markdown'
    )
    
    # Pilih fungsi download berdasarkan platform
    download_funcs = {
        'youtube': download_youtube,
        'tiktok': download_tiktok,
        'instagram': download_instagram,
        'spotify': download_spotify,
    }
    
    # Jalankan download async
    import threading
    def download_thread():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        if platform in download_funcs:
            file_path = loop.run_until_complete(download_funcs[platform](url))
        else:
            file_path = loop.run_until_complete(download_general(url))
        
        # Kirim hasil ke main thread
        context.bot.send_message(chat_id=update.effective_chat.id, 
                                text=f"PROCESS_DONE:{file_path}" if file_path else "PROCESS_FAILED")
    
    threading.Thread(target=download_thread, daemon=True).start()
    
    # Simpan status message untuk update nanti
    context.user_data['status_msg_id'] = status_msg.message_id

def check_download_status(update: Update, context: CallbackContext):
    """Cek status download (callback untuk thread)"""
    # Ini akan dipanggil dari thread, perlu implementasi queue
    pass

def button_callback(update: Update, context: CallbackContext):
    """Handler untuk button inline"""
    query = update.callback_query
    query.answer()
    
    if query.data == 'help':
        query.message.reply_text(
            f"📖 *CARA CEPAT PAKAI HIRAKO BOT*\n\n"
            f"1. Buka YouTube/TikTok/Instagram/Spotify\n"
            f"2. Klik tombol Share → Copy Link\n"
            f"3. Paste link di chat bot ini\n"
            f"4. Tunggu sebentar, file akan terkirim!\n\n"
            f"🎯 *Gampang banget kan?*",
            parse_mode='Markdown'
        )
    elif query.data == 'spotify':
        query.message.reply_text(
            f"🎵 *CARA DOWNLOAD SPOTIFY*\n\n"
            f"1. Buka lagu di Spotify\n"
            f"2. Klik ⋮ (3 titik) → Share → Copy Link\n"
            f"3. Paste link di chat\n"
            f"4. Tunggu proses convert ke MP3\n\n"
            f"⚠️ Butuh waktu 10-30 detik",
            parse_mode='Markdown'
        )
    elif query.data in ['youtube', 'tiktok', 'instagram', 'twitter', 'facebook']:
        query.message.reply_text(
            f"✅ *{query.data.upper()} READY*\n\n"
            f"Kirimkan link video {query.data.upper()} langsung ke chat ini!\n"
            f"Saya akan download otomatis.",
            parse_mode='Markdown'
        )
    elif query.data == 'donasi':
        query.message.reply_text(
            f"❤️ *SUPPORT HIRAKO BOT* ❤️\n\n"
            f"🤖 Bot: @{context.bot.username}\n"
            f"👤 Owner: Hirako\n\n"
            f"Kirim donasi ke:\n"
            f"💰 Saweria: [saweria.co/hirako](https://saweria.co/hirako)\n\n"
            f"Terima kasih telah menggunakan Hirako Bot! 🙏",
            parse_mode='Markdown',
            disable_web_page_preview=True
        )
    
    query.message.delete()

def error_handler(update: Update, context: CallbackContext):
    """Handler error global"""
    logger.error(f"Update {update} caused error {context.error}")

# ========== MAIN ==========
def main():
    """Start the bot"""
    # Buat folder download
    DOWNLOAD_DIR.mkdir(exist_ok=True)
    
    # Buat updater
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
    
    # Start polling
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
