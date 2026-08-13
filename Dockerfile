# ВНИМАНИЕ (Railway): файловая система контейнера эфемерна — при каждом
# деплое contacts.db теряется. Для персистентности подключите volume
# (например, в /data) и задайте переменную DB_PATH=/data/contacts.db.
# Без volume база живёт в /app/contacts.db только до следующего деплоя.
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "main.py"]
