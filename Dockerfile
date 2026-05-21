FROM python:3.11-slim

WORKDIR /app

# Install dependencies untuk yt-dlp
RUN apt-get update && apt-get install -y \
    ffmpeg \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements dan install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy bot
COPY bot.py .

# Run bot
CMD ["python", "bot.py"]
