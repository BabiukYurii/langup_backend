# LangUp — frontend (особистий кабінет)

Мінімальний кабінет на чистих HTML/CSS/JS, який подається самим бекендом
(той самий origin, що й API → без CORS-проблем і з валідним Google-origin).

## Запуск
```bash
uv run python -m app.main      # бек + статика
```
Відкрий: **http://localhost:8000/app/**

## Налаштування Google
1. Створи OAuth Client (Web application) у Google Cloud Console.
2. Додай **Authorized JavaScript origin**: `http://localhost:8000`
3. Встав Client ID у `frontend/config.js` → `GOOGLE_CLIENT_ID`.
4. Додай свій акаунт у **Test users** (поки апка в Testing).

Доки `GOOGLE_CLIENT_ID` порожній — кнопка Google показує підказку, решта кабінету працює.

## Що вміє
- Вхід/реєстрація через Google (`POST /api/auth/google`), збереження JWT у localStorage.
- Завантаження профілю (`GET /api/auth/me`) з авто-рефрешем access-токена.
- Редагування профілю: ім'я, рідна / цільова мова (`PATCH /api/users/{id}`).
- Вихід.
