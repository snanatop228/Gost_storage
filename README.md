

# Система управления ГОСТами (REST API)

Серверная часть на **Flask** для ведения базы нормативных документов (ГОСТ) с поддержкой аутентификации, разграничения ролей, загрузки файлов и расширенного поиска.

## Основные возможности

- Регистрация и аутентификация пользователей (JWT-токен, срок действия 24 часа)
- Роли: `admin`, `user`
- CRUD операции над ГОСТами (создание, чтение, обновление, мягкое удаление)
- Загрузка и скачивание файлов (PDF, DOC, DOCX)
- Поиск по номеру, названию, году, области применения, ключевым словам
- Вывод последних 5 добавленных документов
- Резервное копирование базы данных (только для admin)
- SQLite в качестве хранилища

## Технологии

- Python 3.8+
- Flask
- JWT (PyJWT)
- SQLite3
- Werkzeug (хэширование паролей, secure_filename)

## Установка и запуск

1. **Клонируйте репозиторий**  
   ```bash
   git clone https://github.com/your-repo/gost-api.git
   cd gost-api
   ```

2. **Создайте виртуальное окружение**  
   ```bash
   python -m venv venv
   source venv/bin/activate      # Linux/macOS
   venv\Scripts\activate         # Windows
   ```

3. **Установите зависимости**  
   ```bash
   pip install Flask Flask-CORS PyJWT Werkzeug
   ```

4. **Запустите приложение**  
   ```bash
   python app.py
   ```
   Сервер запустится на `http://localhost:5000`.

> При первом запуске автоматически создаётся база `gosts.db` и пользователь `admin` с паролем `admin123`.

## Эндпоинты API

### Аутентификация и пользователи

| Метод | URL                  | Описание                     | Доступ      |
|-------|----------------------|------------------------------|-------------|
| POST  | `/api/register`      | Регистрация нового пользователя | public    |
| POST  | `/api/login`         | Вход, получение JWT-токена    | public      |

### Работа с ГОСТами (требуется JWT в заголовке `Authorization: Bearer <token>`)

| Метод   | URL                              | Описание                                      | Роль               |
|---------|----------------------------------|------------------------------------------------|--------------------|
| GET     | `/api/gosts`                     | Получить список всех ГОСТов (с поиском по строке `?search=...`) | user, editor, admin |
| GET     | `/api/gosts/advanced`            | Расширенный поиск (`?number=&title=&year=&scope=&keywords=`) | user, editor, admin |
| GET     | `/api/gosts/recent`              | Последние 5 добавленных ГОСТов                  | user, editor, admin |
| GET     | `/api/gosts/<id>`                | Получить конкретный ГОСТ по ID                 | user, editor, admin |
| POST    | `/api/gosts`                     | Создать новый ГОСТ (multipart/form-data)       | editor, admin      |
| PUT     | `/api/gosts/<id>`                | Обновить ГОСТ (multipart/form-data)            | editor, admin      |
| DELETE  | `/api/gosts/<id>`                | Мягкое удаление (архивация)                    | editor, admin      |
| GET     | `/api/uploads/<filename>`        | Скачать прикреплённый файл                     | user, editor, admin |

### Администрирование

| Метод | URL                  | Описание                          | Роль   |
|-------|----------------------|-----------------------------------|--------|
| GET   | `/api/admin/backup`  | Скачать резервную копию базы SQLite | admin  |

## Примеры запросов

### 1. Регистрация
```bash
curl -X POST http://localhost:5000/api/register \
  -H "Content-Type: application/json" \
  -d '{"username": "user1", "password": "pass123"}'
```

### 2. Логин
```bash
curl -X POST http://localhost:5000/api/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "admin123"}'
```
Ответ: `{ "token": "...", "user": {...} }`

### 3. Создание ГОСТа (с файлом)
```bash
curl -X POST http://localhost:5000/api/gosts \
  -H "Authorization: Bearer <token>" \
  -F "number=ГОСТ 12345-2020" \
  -F "title=Межгосударственный стандарт" \
  -F "year=2020" \
  -F "scope=Применяется в промышленности" \
  -F "keywords=стандарт, качество" \
  -F "file=@document.pdf"
```

### 4. Поиск по номеру
```bash
curl -X GET "http://localhost:5000/api/gosts/advanced?number=12345" \
  -H "Authorization: Bearer <token>"
```

## Роли и права

- **user** – может просматривать, скачивать, искать
- **editor** – всё, что user, плюс создание, редактирование, удаление
- **admin** – всё, что editor, плюс резервное копирование БД

## Структура базы данных

### Таблица `users`
- `id` – первичный ключ
- `username` – уникальное имя
- `password` – хэш (Werkzeug)
- `role` – `admin`, `editor`, `user`

### Таблица `gosts`
- `id` – первичный ключ
- `number`, `title` – обязательные поля
- `year` – год (целое число)
- `scope` – область применения
- `keywords` – ключевые слова
- `filename` – имя загруженного файла (в папке `uploads/`)
- `created_at`, `updated_at` – временные метки
- `deleted` – флаг мягкого удаления (0 – активен, 1 – в архиве)

## Загрузка файлов

- Допустимые расширения: `.pdf`, `.doc`, `.docx`
- Максимальный размер: 10 МБ
- Файлы переименовываются по маске `ГГГГММДДЧЧММСС_оригинальное_имя.расширение`
- При обновлении ГОСТа старый файл удаляется с диска

## Примечания

- Для продакшена обязательно смените `SECRET_KEY` и отключите `debug=True`.
- В коде используется `datetime.datetime.utcnow()` – в будущих версиях Python рекомендуется заменить на `datetime.now(timezone.utc)`.
- По умолчанию CORS открыт для любых доменов – при необходимости ограничьте его в `CORS(app, origins=...)`.
