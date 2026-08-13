# Справочник телефонов завода (Telegram-бот)

Приватный бот: добавление контактов, список по цехам, поиск, редактирование и удаление. Python + aiogram 3 + SQLite.

## Запуск локально

```bash
pip install -r requirements.txt
cp .env.example .env   # вписать BOT_TOKEN и ALLOWED_USER_IDS
python main.py
```

## Деплой на Railway

1. Создать проект из этого репозитория — Railway соберёт по Dockerfile.
2. В Variables задать `BOT_TOKEN` и `ALLOWED_USER_IDS`.
3. **Персистентность БД:** подключить volume (например, в `/data`) и задать `DB_PATH=/data/contacts.db`. Без volume база стирается при каждом деплое.
