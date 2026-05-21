import os
import asyncio
import logging
from pathlib import Path
from typing import Optional
import re

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)
import yt_dlp

# ========== KONFIGURASI ==========
TOKEN = os.environ.get("BOT_TOKEN", "")
OWNER_ID = int(os.environ.get("OWNER_ID", "0"))

if not TOKEN:
    raise ValueError("BOT_TOKEN environment variable not set!")

# Path download di Railway (gunakan /tmp)
DOWNLOAD_DIR = Path("/tmp/hirako_downloads")
DOWNLOAD_DIR.mkdir(exist_ok=True)

# Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ========== FUNGSI DOWNLOAD ==========
async def download_video(url: str, platform: str) -> Optional[Path]:
    """Download video menggunakan yt-dlp"""
    output_template = str(DOWNLOAD_DIR / f"%(title)s_%(id)s.%(ext)s")
    
    ydl_opts = {
        "outtmpl": output_template,
        "quiet": True,
        "no_warnings": True,
        "extract_flat": False,
        "ignoreerrors": True,
        "no_check_certificate": True,
    }
    
    # Limit ukuran 45MB (buffer biar aman)
    if platform == "youtube":
        ydl_opts["format"] = "best[height<=480][filesize<45M]/best[filesize<45M]"
    else:
        ydl_opts["format"] = "best[filesize<45M]"
    
    try:
        loop = asyncio.get_event_loop()
        
        def download_sync():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                if info:
                    filename = ydl.prepare_filename(info)
                    if Path(filename).exists():
                        return Path(filename)
                return None
        
        result = await loop.run_in_executor(None, download_sync)
        return result
        
    except Exception as e:
        logger.error(f"Download error for {platform}: {e}")
        return None

def detect_platform(url: str) -> str:
    """Deteksi platform dari URL"""
    url_lower = url.lower()
    if "youtube.com" in url_lower or "youtu.be" in url_lower:
        return "youtube"
    elif "tiktok.com" in url_lower:
        return "tiktok"
    elif "instagram.com" in url_lower:
        return "instagram"
    elif "twitter.com" in url_lower or "x.com" in url_lower:
        return "twitter"
    elif "facebook.com" in url_lower:
        return "facebook"
    return "unknown"

# ========== HANDLER ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler /start"""
    keyboard = [
        [InlineKeyboardButton("📖 Cara Penggunaan", callback_data="help")],
        [InlineKeyboardButton("👤 Owner", url=f"tg://user?id={OWNER_ID}")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"✨ *Hai {update.effective_user.first_name}!*\n\n"
        "🤖 *HIRAKO BOT* - Downloader All Sosmed\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "✅ Support:\n"
        "• YouTube (max 480p)\n"
        "• TikTok (No Watermark)\n"
        "• Instagram\n"
        "• Twitter/X\n"
        "• Facebook\n\n"
        "📤 Kirim link video, saya akan download!",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 *CARA PAKAI HIRAKO BOT*\n\n"
        "1️⃣ Buka YouTube/TikTok/IG\n"
        "2️⃣ Klik Share → Copy Link\n"
        "3️⃣ Paste link di chat ini\n"
        "4️⃣ Tunggu video masuk!\n\n"
        "⚠️ *Note:*\n"
        "• Video max 45MB\n"
        "• YouTube terbatas 480p\n"
        "• Instagram mungkin gagal (butuh login)",
        parse_mode="Markdown"
    )

async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler URL"""
    url = update.message.text.strip()
    platform = detect_platform(url)
    
    if platform == "unknown":
        await update.message.reply_text(
            "❌ *Link tidak dikenali*\n\n"
            "Kirim link dari:\n"
            "YouTube | TikTok | Instagram | Twitter | Facebook",
            parse_mode="Markdown"
        )
        return
    
    # Notifikasi
    status_msg = await update.message.reply_text(
        f"⏳ *Downloading from {platform.upper()}...*\nMohon tunggu sebentar.",
        parse_mode="Markdown"
    )
    
    # Download
    file_path = await download_video(url, platform)
    
    if not file_path or not file_path.exists():
        await status_msg.edit_text(
            f"❌ *Gagal download*\n\n"
            f"Platform: {platform.upper()}\n"
            f"Penyebab: Video terlalu besar (>45MB) atau private.",
            parse_mode="Markdown"
        )
        return
    
    file_size = file_path.stat().st_size / (1024 * 1024)
    
    # Kirim video
    try:
        with open(file_path, "rb") as video:
            await update.message.reply_video(
                video=video,
                caption=f"✅ *Download Berhasil!*\n"
                       f"📌 Platform: {platform.upper()}\n"
                       f"📦 Ukuran: {file_size:.1f} MB\n"
                       f"🤖 @HirakoBot",
                parse_mode="Markdown"
            )
        await status_msg.delete()
    except Exception as e:
        await status_msg.edit_text(f"⚠️ Gagal kirim video: {str(e)[:100]}")
    finally:
        try:
            file_path.unlink()
        except:
            pass

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "help":
        await query.message.reply_text(
            "📖 Kirim link video apapun, bot akan otomatis download!\n\n"
            "Contoh:\n"
            "• https://youtu.be/xxxxx\n"
            "• https://tiktok.com/@user/video/xxx",
            parse_mode="Markdown"
        )
    await query.message.delete()

# ========== MAIN ==========
def main():
    """Start the bot"""
    try:
        # Buat aplikasi dengan timeout yang lebih lama
        application = Application.builder().token(TOKEN).build()
        
        # Add handlers
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))
        application.add_handler(CallbackQueryHandler(button_callback))
        
        # Start bot dengan error handling
        logger.info("🚀 Starting Hirako Bot...")
        application.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)
        
    except Exception as e:
        logger.error(f"Failed to start bot: {e}")
        raise

if __name__ == "__main__":
    main()
