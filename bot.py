import os
import asyncio
import logging
from pathlib import Path
from typing import Optional, Dict
import threading
import queue
import subprocess
import re

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

# Batas ukuran file (200MB = 200 * 1024 * 1024)
MAX_FILE_SIZE = 200 * 1024 * 1024

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

def get_spotify_track_info(url: str) -> Optional[tuple]:
    """Ambil info track dari Spotify menggunakan API gratis"""
    try:
        # Extract track ID dari URL Spotify
        track_id_match = re.search(r'track/([a-zA-Z0-9]+)', url)
        if not track_id_match:
            return None
        
        track_id = track_id_match.group(1)
        
        # Gunakan API Spotify gratis (Spotify API wrapper)
        api_url = f"https://spotify-api.cfapps.eu10.hana.ondemand.com/api/tracks/{track_id}"
        
        try:
            response = requests.get(api_url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                track_name = data.get('name', '')
                artists = data.get('artists', [])
                artist_name = artists[0].get('name', '') if artists else ''
                return (track_name, artist_name)
        except:
            pass
        
        # Fallback: extract dari string URL
        # Format: https://open.spotify.com/track/xxxx?si=yyyy
        return (track_id, "Unknown Artist")
        
    except Exception as e:
        logger.error(f"Get Spotify info error: {e}")
        return None

# ========== FUNGSI DOWNLOAD SPOTIFY (via YouTube) ==========
def download_spotify_sync(url: str) -> Optional[Path]:
    """Download lagu dari Spotify dengan mencari di YouTube"""
    try:
        # Ambil info track dari Spotify
        track_info = get_spotify_track_info(url)
        
        if track_info:
            track_name, artist_name = track_info
            search_query = f"{track_name} {artist_name} audio"
        else:
            # Fallback: gunakan URL sebagai search
            search_query = url
        
        logger.info(f"Searching YouTube for: {search_query}")
        
        # Opsi untuk yt-dlp - download audio dari YouTube
        output_template = str(DOWNLOAD_DIR / f"%(title)s_%(id)s.%(ext)s")
        
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': output_template,
            'quiet': True,
            'no_warnings': True,
            'ignoreerrors': True,
            'default_search': 'ytsearch',  # Search di YouTube
            'noplaylist': True,
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
        }
        
        # Jika track_info ada, cari dengan query spesifik
        if track_info and track_info[0] != track_info[1]:
            search_url = f"ytsearch:{track_info[0]} {track_info[1]} official audio"
        else:
            search_url = url
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                # Coba extract info
                info = ydl.extract_info(search_url, download=True)
                
                if info:
                    # Tunggu proses post-processor selesai
                    import time
                    time.sleep(2)
                    
                    # Cari file mp3 yang dihasilkan
                    mp3_files = list(DOWNLOAD_DIR.glob("*.mp3"))
                    if mp3_files:
                        # Ambil file terbaru
                        latest_mp3 = max(mp3_files, key=lambda f: f.stat().st_mtime)
                        if latest_mp3.stat().st_size > 0 and latest_mp3.stat().st_size < MAX_FILE_SIZE:
                            logger.info(f"Spotify download success: {latest_mp3}")
                            return latest_mp3
                    
                    # Cari file audio lain
                    for ext in ['.m4a', '.webm', '.opus']:
                        audio_files = list(DOWNLOAD_DIR.glob(f"*{ext}"))
                        if audio_files:
                            latest_audio = max(audio_files, key=lambda f: f.stat().st_mtime)
                            if latest_audio.stat().st_size < MAX_FILE_SIZE:
                                return latest_audio
            except Exception as e:
                logger.error(f"yt-dlp search error: {e}")
                
                # Coba lagi dengan query lebih sederhana
                if track_info:
                    simple_query = f"ytsearch:{track_info[0]}"
                    info = ydl.extract_info(simple_query, download=True)
                    if info:
                        time.sleep(2)
                        mp3_files = list(DOWNLOAD_DIR.glob("*.mp3"))
                        if mp3_files:
                            latest_mp3 = max(mp3_files, key=lambda f: f.stat().st_mtime)
                            return latest_mp3
        
        return None
    except Exception as e:
        logger.error(f"Spotify download error: {e}")
        return None

# ========== FUNGSI DOWNLOAD VIDEO ==========
def download_video_sync(url: str, platform: str) -> Optional[Path]:
    """Download video secara synchronous (untuk dijalankan di thread)"""
    output_template = str(DOWNLOAD_DIR / f"%(title)s_%(id)s.%(ext)s")
    
    # Format dengan batas 200MB
    ydl_opts = {
        'format': f'best[filesize<{MAX_FILE_SIZE}]',
        'outtmpl': output_template,
        'quiet': True,
        'no_warnings': True,
        'ignoreerrors': True,
        'noplaylist': True,
    }
    
    # Khusus YouTube batasi 720p
    if platform == 'youtube':
        ydl_opts['format'] = f'best[height<=720][filesize<{MAX_FILE_SIZE}]/best[filesize<{MAX_FILE_SIZE}]'
    
    # Untuk TikTok dan Instagram
    if platform in ['tiktok', 'instagram']:
        ydl_opts['format'] = f'best[filesize<{MAX_FILE_SIZE}]'
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if info:
                filename = ydl.prepare_filename(info)
                
                # Cek file exist
                if Path(filename).exists() and Path(filename).stat().st_size < MAX_FILE_SIZE:
                    return Path(filename)
                
                # Coba cari file dengan ekstensi berbeda
                for ext in ['.mp4', '.webm', '.mkv']:
                    test_path = Path(str(filename).rsplit('.', 1)[0] + ext)
                    if test_path.exists() and test_path.stat().st_size < MAX_FILE_SIZE:
                        return test_path
                
                # Cari file terbaru di folder download
                files = list(DOWNLOAD_DIR.glob("*"))
                if files:
                    latest_file = max(files, key=lambda f: f.stat().st_mtime)
                    if latest_file.stat().st_size < MAX_FILE_SIZE:
                        return latest_file
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
            
            logger.info(f"Processing {platform} download for chat {chat_id}")
            
            # Pilih fungsi download berdasarkan platform
            if platform == 'spotify':
                file_path = download_spotify_sync(url)
            else:
                file_path = download_video_sync(url, platform)
            
            # Kirim hasil
            if file_path and file_path.exists() and file_path.stat().st_size < MAX_FILE_SIZE:
                file_size_mb = file_path.stat().st_size / (1024 * 1024)
                
                # Kirim file
                try:
                    # Untuk Spotify atau file MP3 kirim sebagai audio
                    if platform == 'spotify' or file_path.suffix == '.mp3':
                        with open(file_path, 'rb') as audio:
                            context.bot.send_audio(
                                chat_id=chat_id,
                                audio=audio,
                                caption=f"✅ *Download Berhasil!*\n"
                                       f"📌 Platform: SPOTIFY (via YouTube)\n"
                                       f"📦 Ukuran: {file_size_mb:.1f} MB\n"
                                       f"🤖 @{context.bot.get_me().username}",
                                parse_mode='Markdown',
                                timeout=120,
                                title=file_path.stem[:50]
                            )
                    else:
                        # Kirim sebagai video
                        with open(file_path, 'rb') as video:
                            context.bot.send_video(
                                chat_id=chat_id,
                                video=video,
                                caption=f"✅ *Download Berhasil!*\n"
                                       f"📌 Platform: {platform.upper()}\n"
                                       f"📦 Ukuran: {file_size_mb:.1f} MB\n"
                                       f"🤖 @{context.bot.get_me().username}",
                                parse_mode='Markdown',
                                timeout=120,
                                supports_streaming=True
                            )
                    
                    # Hapus status message
                    try:
                        context.bot.delete_message(chat_id=chat_id, message_id=status_msg_id)
                    except:
                        pass
                    
                    logger.info(f"Successfully sent {platform} file to chat {chat_id}")
                    
                except Exception as e:
                    logger.error(f"Send file error: {e}")
                    error_msg = str(e)
                    if "File is too large" in error_msg:
                        error_text = "⚠️ *File terlalu besar untuk Telegram!*\nMaksimal 200MB"
                    else:
                        error_text = f"⚠️ Gagal mengirim file: {str(e)[:100]}"
                    
                    context.bot.send_message(
                        chat_id=chat_id,
                        text=error_text,
                        parse_mode='Markdown'
                    )
                
                # Hapus file
                try:
                    file_path.unlink()
                except:
                    pass
            else:
                # Gagal download
                error_detail = ""
                if platform == 'spotify':
                    error_detail = "\n• Lagu tidak ditemukan di YouTube\n• Coba lagu yang lebih populer"
                
                try:
                    context.bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=status_msg_id,
                        text=f"❌ *Gagal Download!*\n\n"
                             f"Platform: {platform.upper()}\n"
                             f"Penyebab:\n"
                             f"• File terlalu besar (>200MB)\n"
                             f"• Link private/expired\n"
                             f"• Server sedang sibuk{error_detail}\n\n"
                             f"Coba link lain ya!",
                        parse_mode='Markdown'
                    )
                except:
                    pass
                
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
        f"📤 *Kirim link*, saya download!\n"
        f"📦 *Max file:* 200MB\n\n"
        f"🎵 *Spotify Note:* Mencari lagu di YouTube",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

def help_command(update: Update, context: CallbackContext):
    update.message.reply_text(
        f"📖 *PANDUAN HIRAKO BOT*\n\n"
        f"1️⃣ *Copy link* dari aplikasi\n"
        f"2️⃣ *Paste link* di chat ini\n"
        f"3️⃣ *Tunggu* 10-30 detik\n"
        f"4️⃣ *File terkirim* otomatis!\n\n"
        f"⚠️ *BATASAN:*\n"
        f"• File max 200MB\n"
        f"• YouTube 720p\n"
        f"• Spotify: mencari versi audio di YouTube\n\n"
        f"💡 Link harus *public*!",
        parse_mode='Markdown'
    )

def donasi_command(update: Update, context: CallbackContext):
    update.message.reply_text(
        f"❤️ *DUKUNG HIRAKO BOT* ❤️\n\n"
        f"Bot ini *GRATIS*!\n\n"
        f"💰 *Saweria:* [saweria.co/hirako](https://saweria.co/hirakoxs)\n\n"
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
    
    # Pesan khusus Spotify
    if platform == 'spotify':
        status_text = f"{emoji} *Mencari lagu di YouTube...*\n" \
                      f"⏳ Mengambil audio dari {url[:40]}...\n\n" \
                      f"_Proses bisa 20-40 detik_"
    else:
        status_text = f"{emoji} *Mendownload dari {platform.upper()}...*\n" \
                      f"⏳ Mohon tunggu sebentar...\n\n" \
                      f"_Proses download bisa 10-30 detik_"
    
    # Kirim pesan status
    status_msg = update.message.reply_text(
        status_text,
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
            f"4. Tunggu file masuk!\n\n"
            f"🎯 *Mudah kan?*",
            parse_mode='Markdown'
        )
    elif query.data == 'spotify':
        query.edit_message_text(
            f"🎵 *DOWNLOAD SPOTIFY*\n\n"
            f"1. Buka lagu di Spotify\n"
            f"2. ⋮ → Share → Copy Link\n"
            f"3. Paste link di chat\n"
            f"4. Bot akan mencari lagu di YouTube\n"
            f"5. Convert ke MP3 dan kirim\n\n"
            f"⏱️ Butuh 20-40 detik\n"
            f"📦 Hasil: MP3 192kbps",
            parse_mode='Markdown'
        )
    elif query.data == 'donasi':
        query.edit_message_text(
            f"❤️ *SUPPORT HIRAKO BOT* ❤️\n\n"
            f"💰 Saweria: [saweria.co/hirako](https://saweria.co/hirakoxs)\n\n"
            f"Terima kasih! 🙏",
            parse_mode='Markdown',
            disable_web_page_preview=True
        )
    elif query.data in ['youtube', 'tiktok', 'instagram', 'twitter', 'facebook']:
        query.edit_message_text(
            f"✅ *{query.data.upper()} READY*\n\n"
            f"Kirim link video {query.data.upper()} langsung ke chat!\n"
            f"📦 Max 200MB",
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
    logger.info(f"Download dir: {DOWNLOAD_DIR}")
    logger.info(f"Max file size: {MAX_FILE_SIZE / (1024*1024):.0f}MB")
    
    # Start polling
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
