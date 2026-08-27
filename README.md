# Совет — Система голосований

Discord-бот и веб-панель для создания, публикации, проведения и автоматического учёта голосований Совета.

---

## Что нужно установить

1. **Python 3.11+** — https://www.python.org/downloads/ (поставить галочку "Add to PATH")

---

## Шаг 1: Получение токена Discord

1. https://discord.com/developers/applications
2. **New Application** → ввести название → **Create**
3. Левое меню → **Bot** → **Add Bot**
4. Скопировать **Token** (нажать Copy)
5. Левое меню → **OAuth2** → скопировать **Client ID** и **Client Secret**
6. В разделе **Bot** включить:
   - `MESSAGE CONTENT Intent`
   - `SERVER MEMBERS Intent`

### Приглашение бота на сервер

1. **OAuth2** → **URL Generator**
2. Scopes: `bot`, `applications.commands`
3. Bot Permissions: `Send Messages`, `Embed Links`, `Use Slash Commands`, `Manage Messages`, `Read Message History`
4. Скопировать URL → открыть в браузере → выбрать сервер

---

## Шаг 2: Установка и запуск

Открыть терминал в папке проекта:

```bash
cd D:\PROJECTS\botself

# Создать виртуальное окружение
python -m venv venv
venv\Scripts\activate

# Установить зависимости
pip install -r requirements.txt
```

---

## Шаг 3: Настройка .env

Открыть файл `.env` и вписать свой токен:

```
DISCORD_BOT_TOKEN=СЮДА_ТОКЕН_БОТА
DISCORD_CLIENT_ID=СЮДА_CLIENT_ID
DISCORD_CLIENT_SECRET=СЮДА_CLIENT_SECRET
DISCORD_REDIRECT_URI=http://localhost:8000/api/auth/callback
DATABASE_URL=sqlite+aiosqlite:///data/council_votes.db
LOG_LEVEL=INFO
TZ=Europe/Moscow
```

---

## Шаг 4: Миграция базы данных

```bash
alembic upgrade head
```

---

## Шаг 5: Запуск бота

```bash
python -m bot
```

Должно появиться:
```
Бот запущен как ИмяБота (ID: ...)
Синхронизировано 32 команд
```

---

## Шаг 6: Запуск веб-панели (отдельный терминал)

```bash
uvicorn web.app:app --host 0.0.0.0 --port 8000
```

Открыть http://localhost:8000

---

## Первая настройка в Discord

В канале для голосований:

```
/configure council_role:@РольСовета
/configure admin_role:@РольАдминов
/configure vote_channel:#голосования
/sync_members
/setup_panel
```

Заменить `@РольСовета` и `@РольАдминов` на реальные роли сервера.

---

## Все команды

### Создание и управление

| Команда | Описание |
|---|---|
| `/create_vote` | Создать голосование |
| `/publish_vote <id>` | Опубликовать |
| `/cancel_vote <id>` | Отменить |
| `/complete_vote <id>` | Завершить досрочно |
| `/vote_clone <id>` | Скопировать |
| `/vote_edit <id>` | Редактировать черновик |
| `/vote_pause <id>` | Приостановить |
| `/vote_resume <id>` | Возобновить |
| `/vote_extend <id>` | Продлить |
| `/vote_veto <id>` | Наложить вето |

### Информация

| Команда | Описание |
|---|---|
| `/active_votes` | Активные голосования |
| `/vote_info <id>` | Подробная информация |
| `/vote_history` | История завершённых |
| `/vote_search` | Поиск |
| `/vote_status` | Сводка |
| `/vote_comments <id>` | Комментарии |
| `/vote_veto_list <id>` | Список вето |

### Участники

| Команда | Описание |
|---|---|
| `/council_list` | Состав Совета |
| `/sync_members` | Синхронизировать роли |
| `/my_stats` | Личная статистика |
| `/leaderboard` | Рейтинг |

### Действия

| Команда | Описание |
|---|---|
| `/vote_comment <id>` | Комментарий |
| `/vote_remind <id>` | Напоминание |
| `/vote_export <id>` | Экспорт JSON/CSV |
| `/vote_weight` | Вес голоса |

### Шаблоны

| Команда | Описание |
|---|---|
| `/template_create` | Создать шаблон |
| `/template_list` | Список шаблонов |
| `/template_use <id>` | Голосование из шаблона |
| `/template_delete <id>` | Удалить шаблон |

### Настройки

| Команда | Описание |
|---|---|
| `/configure` | Настройки сервера |
| `/setup_panel` | Панель в канал |
