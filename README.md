# TGShopBot — Telegram-бот витрина

Telegram-бот для перепродажи цифровых товаров, ИИ-подписок, Telegram Premium, пополнения Steam через Partner API магазина [thegodapishop.xyz](https://thegodapishop.xyz).

## Возможности

- 🛒 **Каталог по категориям** — подписки на нейросети (ChatGPT, Claude, Gemini, Perplexity) и медиа-сервисы (Spotify, CapCut, Duolingo)
- 🎮 **Steam** — пополнение кошелька
- 🎮 **Игры** — покупка по variation_id
- 💰 **Баланс** — внутренний баланс пользователей
- 💳 **Платежные шлюзы** — оплата банковскими картами, СБП и через CryptoBot
- 📜 **История** — все заказы с пагинацией
- 👑 **Админ-панель** — управление балансами, депозитами, рассылки

## Быстрый старт

### 1. Клонирование и настройка

```bash
git clone <repo>
cd TGShopBot
cp .env.example .env
```

Заполните `.env`:

| Переменная | Описание |
|---|---|
| `BOT_TOKEN` | Токен Telegram-бота от @BotFather |
| `PARTNER_API_KEY` | Ключ партнёра (PRTNR-...) |
| `PARTNER_API_BASE` | URL API (по умолчанию https://api.thegodapishop.xyz) |
| `DATABASE_URL` | Строка подключения к БД |
| `MARKUP_PERCENT` | Наценка в % (по умолчанию 15) |
| `ADMIN_IDS` | Telegram ID администраторов через запятую |
| `LOG_LEVEL` | Уровень логирования (INFO/DEBUG) |
| `RATE_LIMIT_PER_SEC` | Лимит запросов к API/сек (по умолчанию 8) |
| `CRYPTOBOT_TOKEN` | Токен из [@CryptoBot](https://t.me/CryptoBot) -> Crypto Pay -> Create App (опционально) |
| `YOOKASSA_SHOP_ID` | Идентификатор магазина ЮKassa для оплаты картами/СБП (опционально) |
| `YOOKASSA_SECRET_KEY` | Секретный ключ ЮKassa (опционально) |

### 2. Запуск через Docker

```bash
docker-compose up -d --build
```

### 3. Запуск локально

```bash
pip install -r requirements.txt
python -m bot.main
```

## Команды администратора

| Команда | Описание |
|---|---|
| `/partner_balance` | Баланс партнёра в магазине |
| `/partner_history [limit]` | История операций партнёра |
| `/topup_user <tg_id> <сумма>` | Пополнить баланс пользователя |
| `/deposit_crypto <сумма_руб>` | Создать крипто-депозит |
| `/deposit_ton <сумма_руб>` | Создать TON-депозит |
| `/check_deposit <deposit_id>` | Проверить статус депозита |
| `/broadcast <текст>` | Рассылка всем пользователям |

## Архитектура

```
bot/
├── main.py              # Точка входа
├── config.py            # Pydantic Settings
├── logging_config.py    # Structlog
├── handlers/            # Обработчики сообщений
│   ├── start.py         # /start, помощь, навигация
│   ├── catalog.py       # Каталог подписок по категориям
│   ├── payment.py       # Пополнение баланса (Карты, СБП, CryptoBot)
│   ├── order.py         # Steam / Игры
│   ├── balance.py       # Баланс пользователя
│   ├── history.py       # История заказов
│   └── admin.py         # Админ-команды
├── keyboards/
│   └── kb.py            # Все клавиатуры
├── middlewares/
│   ├── throttling.py    # Анти-флуд
│   └── user_context.py  # Загрузка пользователя из БД
├── services/
│   ├── partner_api.py   # Клиент Partner API
│   ├── orders.py        # Бизнес-логика заказов
│   ├── pricing.py       # Наценка
│   └── background.py    # Фоновые задачи
├── db/
│   ├── models.py        # SQLAlchemy модели
│   ├── engine.py        # Подключение к БД
│   └── repo.py          # Репозитории
└── utils/
    └── formatting.py    # Форматирование
```

## Бизнес-логика

### Ценообразование
- Цена пользователя = цена партнёра × (1 + MARKUP_PERCENT/100), округление вверх до 1 ₽

### Заказы каталога (синхронные)
1. Проверка баланса → списание → вызов API → выдача ключа
2. При ошибке API — автоматический возврат средств

### Внешние заказы (асинхронные)
1. Steam / Игры → заказ уходит в `processing`
2. Фоновый polling каждые 15 сек проверяет статус
3. `success` → уведомление пользователю
4. `failed` → возврат на баланс + уведомление
5. `uncertain` → заморозка средств + алерт админу

### Безопасность
- API-ключ только в `.env`
- Rate-limit 8 req/s (ниже серверного 10)
- Ретраи с exponential backoff на 429 и 5xx
- Транзакции БД: списание + заказ атомарно
- Валидация всего ввода пользователей

## Лицензия

Проприетарный проект.
