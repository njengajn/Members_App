FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD sh -c '
set -ex

echo "===== ENVIRONMENT ====="
env | sort

echo "===== MIGRATE ====="
python manage.py migrate

echo "===== COLLECTSTATIC ====="
python manage.py collectstatic --noinput

echo "===== START GUNICORN ====="
exec gunicorn backend.core.wsgi:application \
    --bind 0.0.0.0:${PORT:-8080}
'