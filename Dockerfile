FROM python:3.11-slim

# ffmpeg (usado via shutil.which("ffmpeg")) + libsndfile (necessário pro soundfile/librosa)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# O Render injeta a variável $PORT — o gunicorn precisa escutar nela
# 1 worker + threads: os jobs ficam na memória (dict jobs) e precisam ser vistos
# pelo mesmo processo que responde /status. Com 2 workers, o status às vezes
# dizia "Job não encontrado" e a memória dobrava.
CMD gunicorn --bind 0.0.0.0:$PORT --timeout 600 --workers 1 --threads 4 app:app
