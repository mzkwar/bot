FROM mcr.microsoft.com/playwright/python:v1.40.0-jammy

WORKDIR /app

# نسخ ملف المتطلبات أولاً لتثبيتها
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# نسخ باقي ملفات المشروع
COPY . .

CMD gunicorn --bind 0.0.0.0:$PORT bot:app --workers 1 --threads 4 --timeout 120
