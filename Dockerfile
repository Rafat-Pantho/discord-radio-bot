FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# ffmpeg for audio, libopus for voice encoding, libsodium for voice encryption
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg libopus0 libsodium23 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY music_bot.py .

RUN useradd --create-home bot
USER bot

CMD ["python", "music_bot.py"]
