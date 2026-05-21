import os
import re
import asyncio
import logging
from pathlib import Path
from typing import Optional

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
TOKEN = os.environ.get("BOT_TOKEN", "PASTE_BOT_TOKEN_ANDA_DISINI")
OWNER_ID = int(os.environ.get("OWNER_ID", "123456789"))

# Path download di Railway (gunakan /tmp karena read-only di production)
DOWNLOAD_DIR = Path("/tmp/downloads")
DOWNLOAD_DIR.mkdir(exist_ok=True)

# Cookies untuk Instagram (opsional, letakkan di /app/cookies.txt)
COOKIES_FILE = "cookies.txt" if os.path.exists("cookies.txt") else None

# Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", 
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ========== FUNGSI DOWNLOAD ==========
async def download_video(url: str, platform: str) -> Optional[Path]:
    """Download video menggunakan yt-dlp, return path file."""
    output_template = str(DOWNLOAD_DIR / f"%(title)s_%(id)s.%(ext)s")
    
    ydl_opts = {
        "outtmpl": output_template,
        "quiet": True,
        "no_warnings": True,
        "extract_flat": False,
        "force_generic_extractor": False,
        "ignoreerrors": True,
        "no_check_certificate": True,
        "prefer_insecure": True,
    }
    
    # Konfigurasi per platform dan limit ukuran
    if platform == "youtube":
        ydl_opts["format"] = "bestvideo[height<=480][filesize<50M]+bestaudio[filesize<50M]/best[height<=480][filesize<50M]"
    elif platform == "tiktok":
        ydl_opts["format"] = "best[filesize<50M]"
    elif platform == "instagram":
        ydl_opts["format"] = "best[filesize<50M]"
        if COOKIES_FILE:
            ydl_opts["cookiefile"] = COOKIES_FILE
    else:
        ydl_opts["format"] = "best[filesize<50M]"
    
    try:
        loop = asyncio.get_event_loop()
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = await loop.run_in_executor(None, ydl.extract_info, url, True)
            
            if not info:
                return None
                
            filename = ydl.prepare_filename(info)
            
            # Cek berbagai kemungkinan ekstensi
            possible_files = [filename]
            for ext in [".mp4", ".webm", ".mkv", ".mp4.webm"]:
                possible_files.append(str(filename).replace(".webm", ext).replace(".mkv", ".mp4"))
            
            for f in possible_files:
                if Path(f).exists():
                    return Path(f)
            
            # Cari file di folder download
            for f in DOWNLOAD_DIR.glob("*"):
                if f.stat().st_size < 50 * 1024 * 1024:  # max 50MB
                    return f
                    
            return None
    except Exception as e:
        logger.error(f"Download error: {e}")
        return None

def detect_platform(url: str) -> str:
    """Deteksi platform dari URL."""
    url_lower = url.lower()
    if "youtube.com" in url_lower or "youtu.be" in url_lower:
        return "youtube"
    elif "tiktok.com" in url_lower or "vt.tiktok.com" in url_lower:
        return "tiktok"
    elif "instagram.com" in url_lower or "instagr.am" in url_lower:
        return "instagram"
    elif "twitter.com" in url_lower or "x.com" in url_lower:
        return "twitter"
    elif "facebook.com" in url_lower or "fb.watch" in url_lower:
        return "facebook"
    elif "pinterest.com" in url_lower or "pin.it" in url_lower:
        return "pinterest"
    else:
        return "unknown"

# ========== HANDLER BOT ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler /start - menu utama dengan button kece"""
    keyboard = [
        [InlineKeyboardButton("📥 Cara Download", callback_data="help")],
        [InlineKeyboardButton("📢 Channel Update", url="https://t.me/hirako_updates")],
        [InlineKeyboardButton("⭐ Support Bot", callback_data="donasi")],
        [InlineKeyboardButton("👤 Owner", url=f"tg://user?id={OWNER_ID}")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"✨ *HAI {update.effective_user.first_name.upper()}!* ✨\n\n"
        "🤖 *HIRAKO BOT* - Premium Downloader All Sosmed\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "📌 *SUPPORTED PLATFORM:*\n"
        "🔹 YouTube (max 480p)\n"
        "🔹 TikTok (No Watermark)\n"
        "🔹 Instagram (Reels/Posts)\n"
        "🔹 Twitter/X\n"
        "🔹 Facebook\n"
        "🔹 Pinterest\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "💬 *CARPAKAI:*\n"
        "Kirimkan link video apapun, saya akan download otomatis!\n\n"
        "_⚡ Fast | 🎯 Accurate | 🔒 Safe_",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 *PANDUAN HIRAKO BOT*\n\n"
        "✏️ *LANGKAH-LANGKAH:*\n"
        "1️⃣ Copy link video dari aplikasi (YouTube/TikTok/IG dll)\n"
        "2️⃣ Paste link di chat ini\n"
        "3️⃣ Tunggu 5-15 detik\n"
        "4️⃣ Video akan terkirim otomatis!\n\n"
        "⚠️ *BATASAN:*\n"
        "▸ Maksimal 50MB (kebijakan Telegram)\n"
        "▸ YouTube dibatasi 480p untuk kecepatan\n"
        "▸ Instagram butuh login (terkadang gagal)\n\n"
        "💡 *TIPS:* Kirim link yang *public* ya!",
        parse_mode="Markdown"
    )

async def donasi_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text(
        "❤️ *DUKUNG HIRAKO BOT* ❤️\n\n"
        "Bot ini gratis selamanya! Tapi jika ingin donasi:\n\n"
        "💰 *Saweria:* [saweria.co/hirako](https://saweria.co/hirako)\n"
        "💎 *Dana:* 08123456789\n"
        "🪙 *Trakteer:* [trakteer.id/hirako](https://trakteer.id/hirako)\n\n"
        "Terima kasih sudah menggunakan Hirako Bot! 🙏\n"
        "_Dukunganmu membuat bot ini tetap hidup_",
        parse_mode="Markdown",
        disable_web_page_preview=True
    )

async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler URL masuk"""
    url = update.message.text.strip()
    platform = detect_platform(url)
    
    if platform == "unknown":
        await update.message.reply_text(
            "❌ *LINK TIDAK DIKENALI*\n\n"
            "Kirim link dari:\n"
            "✓ YouTube\n✓ TikTok\n✓ Instagram\n✓ Twitter\n✓ Facebook\n✓ Pinterest\n\n"
            "Contoh: `https://youtu.be/xxxxx`",
            parse_mode="Markdown"
        )
        return
    
    # Emoji platform
    emoji_map = {
        "youtube": "▶️", "tiktok": "🎵", "instagram": "📸",
        "twitter": "🐦", "facebook": "👥", "pinterest": "📌"
    }
    emoji = emoji_map.get(platform, "📹")
    
    # Notifikasi proses
    status_msg = await update.message.reply_text(
        f"{emoji} *Mendownload dari {platform.upper()}...*\n"
        f"🔗 `{url[:50]}...`\n\n"
        f"⏳ Mohon tunggu, sedang diproses...",
        parse_mode="Markdown"
    )
    
    # Download
    file_path = await download_video(url, platform)
    
    if not file_path or not file_path.exists() or file_path.stat().st_size == 0:
        await status_msg.edit_text(
            f"❌ *GAGAL DOWNLOAD*\n\n"
            f"Platform: {platform.upper()}\n"
            f"Kemungkinan penyebab:\n"
            f"• Video terlalu besar (>50MB)\n"
            f"• Video private/delete\n"
            f"• Instagram butuh login\n\n"
            f"Coba link lain atau gunakan platform lain.",
            parse_mode="Markdown"
        )
        return
    
    file_size = file_path.stat().st_size / (1024 * 1024)
    
    # Kirim video dengan caption kece
    try:
        with open(file_path, "rb") as video_file:
            await update.message.reply_video(
                video=video_file,
                caption=f"✅ *DOWNLOAD BERHASIL!*\n\n"
                       f"📌 *Platform:* {platform.upper()}\n"
                       f"📦 *Ukuran:* {file_size:.2f} MB\n"
                       f"🤖 *Bot:* @{context.bot.username}\n\n"
                       f"✨ *Terima kasih sudah menggunakan Hirako Bot!*",
                parse_mode="Markdown"
            )
        await status_msg.delete()
    except Exception as e:
        logger.error(f"Send error: {e}")
        await status_msg.edit_text(
            f"⚠️ *GAGAL MENGIRIM VIDEO*\n\n"
            f"Error: {str(e)[:100]}\n\n"
            f"Kemungkinan video terlalu besar atau format tidak didukung.",
            parse_mode="Markdown"
        )
    finally:
        # Hapus file setelah dikirim
        try:
            if file_path and file_path.exists():
                os.unlink(file_path)
        except:
            pass

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "help":
        await query.message.reply_text(
            "📖 *CARCEP HIRAKO BOT*\n\n"
            "1. Buka aplikasi (YouTube/TikTok/IG)\n"
            "2. Klik share → Copy link\n"
            "3. Paste di chat bot ini\n"
            "4. Tunggu video masuk!\n\n"
            "🎯 *GAMPANG BANGET KAN?*",
            parse_mode="Markdown"
        )
    elif query.data == "donasi":
        await query.message.reply_text(
            "❤️ *SUPPORT HIRAKO BOT* ❤️\n\n"
            "Kirim donasi berapapun ke:\n"
            "💰 Saweria: [saweria.co/hirako](https://saweria.co/hirako)\n\n"
            "Makasih banyak! 🙏",
            parse_mode="Markdown",
            disable_web_page_preview=True
        )
    
    await query.message.delete()

# ========== MAIN ==========
def main():
    """Start the bot."""
    # Buat folder download jika belum ada
    DOWNLOAD_DIR.mkdir(exist_ok=True)
    
    # Buat aplikasi
    application = Application.builder().token(TOKEN).build()
    
    # Command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    
    # URL handler (filter text yang bukan command)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))
    
    # Button callback
    application.add_handler(CallbackQueryHandler(button_callback))
    
    # Start bot
    logger.info("🚀 Hirako Bot started successfully!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
