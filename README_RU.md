# Signal Radar — Инструкция

## Быстрый старт

Двойной клик на `start.bat` или запусти в PowerShell:

```powershell
.\start.ps1
```

Система запустит:
- **Backend API** на http://localhost:8000
- **Worker scheduler** — сбор и анализ сигналов
- **Frontend** на http://localhost:3000
- Откроет дашборд в браузере

## Остановка

```powershell
.\stop.ps1
```

Или просто закрой окна / перезагрузи ноутбук.

## Проверка статуса

```powershell
.\status.ps1
```

Покажет:
- Работает ли backend / frontend / worker
- Количество сигналов в базе
- Последнюю активность из логов
- Использование памяти

## Автозапуск при включении ноутбука

Один раз запусти от имени администратора:

```powershell
# ПКМ на PowerShell -> Запуск от имени администратора
.\install_autostart.ps1
```

После этого Signal Radar будет стартовать автоматически при входе в Windows.

Чтобы убрать автозапуск:

```powershell
Unregister-ScheduledTask -TaskName "SignalRadar"
```

## Telegram-бот

1. Открой Telegram, найди **@BotFather**
2. Отправь `/newbot`, придумай имя
3. Скопируй токен (выглядит как `123456:ABC-DEF...`)
4. Добавь в файл `backend/.env`:
   ```
   TELEGRAM_BOT_TOKEN=твой_токен_здесь
   ```
5. Перезапусти: закрой всё через `stop.ps1`, потом `start.bat`
6. Напиши своему боту `/start`

### Команды бота

| Команда | Что делает |
|---------|-----------|
| `/top` | 5 сильнейших сигналов |
| `/new` | Последние новые сигналы |
| `/rising` | Растущие тренды |
| `/breakout` | Критические тренды 🚨 |
| `/status` | Статус системы |
| `/radars` | Твои радары |
| `/mute 2` | Заглушить алерты на 2 часа |
| `/help` | Помощь |

## Структура проекта

```
Project/
├── start.bat              ← двойной клик для запуска
├── start.ps1              ← скрипт запуска
├── stop.ps1               ← скрипт остановки
├── status.ps1             ← проверка статуса
├── install_autostart.ps1  ← установка автозапуска (1 раз)
├── backend/               ← FastAPI + worker
│   ├── .env               ← настройки и токены
│   ├── .venv/             ← Python виртуальное окружение
│   └── app/
│       ├── main.py        ← API сервер
│       └── workers/       ← сборщики сигналов
├── frontend/              ← Next.js дашборд
└── logs/                  ← логи (создаётся автоматически)
    ├── startup.log
    ├── backend.log
    ├── backend_err.log
    ├── worker.log
    ├── worker_err.log
    ├── frontend.log
    └── frontend_err.log
```

## Ссылки

- **Дашборд:** http://localhost:3000
- **API документация:** http://localhost:8000/docs
- **Логи:** `.\logs\`

## Решение проблем

**Backend не запускается:**
```powershell
# Проверь лог ошибок
Get-Content .\logs\backend_err.log -Tail 20
```

**Frontend не запускается:**
```powershell
# Проверь что npm установлен
npm --version
# Проверь лог
Get-Content .\logs\frontend_err.log -Tail 20
```

**Порт занят:**
```powershell
# Узнай кто занимает порт 8000
netstat -ano | findstr :8000
# Убей процесс
.\stop.ps1
```

**Переустановка зависимостей:**
```powershell
# Backend
cd backend
.\.venv\Scripts\pip install -r requirements.txt

# Frontend
cd frontend
npm install
```
