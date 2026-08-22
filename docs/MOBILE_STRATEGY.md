# LangUp Mobile — стратегія Flutter-застосунку

Документ описує заміну поточного веб-кабінету (`frontend/`, віддається на `/app`)
нативним мобільним застосунком на **Flutter**. Аналіз зроблено по коду бекенду
(`app/`) і фронтенду (`frontend/`), не з припущень.

> Статус: план (ще не реалізовано). Мобільний застосунок = окремий git-репозиторій
> `langup_mobile`. Бекенд лишається як є; зміни на сервері мінімальні й перелічені нижче.

---

## 1. Що ми замінюємо і що лишається

Поточний UI — статичні HTML/JS у `frontend/`, стан у `localStorage`, віддається
бекендом на `/app`. Уся бізнес-логіка вже за API під префіксом **`/api`**.

**Замінюємо мобільним застосунком** (кабінет учня):
- логін / реєстрація / Google (`index.html`, `app.js`)
- словник (`words.html`, `words.js`)
- практика — 5 типів вправ (`practice.html`, `practice.js`)
- повторення SM-2 (`review.html`, `review.js`)
- дашборд (`dashboard.html`, `dashboard.js`)
- профіль + підписка (`app.js`)

**Лишається у вебі (мобільний застосунок НЕ дублює):**
- адмінка (`admin.html`) — рідко, десктопна
- Stripe Checkout / Customer Portal — hosted-сторінки Stripe
- лендинги email verify / reset password (бекенд редіректить у веб)
- браузерне розширення (захоплення слів на десктопі)

Мобільний аналог розширення — **share-sheet** («Поділитися текстом» → додати слово).

---

## 2. Контракти API (усе під `/api`)

Джерело правди — `/openapi.json` бекенду. З нього генеруємо Dart-моделі й клієнт
(див. §6), тому нижче — лише орієнтир, не переписуємо вручну.

### Auth (`app/routers/auth.py`)
- `POST /auth/register` `{email, password, full_name?}` → `TokenPair {access_token, refresh_token, token_type}` (201)
- `POST /auth/login` `{email, password}` → `TokenPair`
- `POST /auth/google` `{id_token}` → `TokenPair` (той самий id_token, що дає нативний google_sign_in)
- `POST /auth/refresh` `{refresh_token}` → `TokenPair` — **ROTATING**: токен одноразовий, повторне використання розлогінює всюди
- `POST /auth/forgot-password` `{email}` → 202 (завжди однаково, без розкриття існування акаунта)
- `POST /auth/reset-password` `{token, password}` — токен з email-листа (веб-сторінка)
- `GET /auth/verify-email?token=` → редірект у веб
- `POST /auth/verify-email/resend` (auth) → 202
- `POST /auth/logout` `{refresh_token}`, `POST /auth/logout-all` (auth)
- `GET /auth/me` → `UserOut`

### Профіль / користувач (`app/routers/user.py`)
- `PATCH /users/{id}` `{full_name?, native_language?, target_language?, preferences?}` → `UserOut`
- `UserOut`: `id, email, full_name, role, status, is_email_verified, native_language, target_language, preferences, created_at, updated_at`
- **Гейт:** новий акаунт без `native_language` мусить обрати рідну мову до входу в кабінет (див. `routeAfterAuth` в `app.js`).

### Словник / захоплення (`app/routers/capture.py`)
- `POST /vocabulary` `{word, language, sentence?, source_url?, source_title?}` → `UserWordOut` (201)
- `GET /vocabulary?page=&limit=&query=&language=` → `Page[UserWordOut]`
- `GET /vocabulary/languages` → `[{language, count}]` (джерело перемикача мов)
- `GET /vocabulary/{uuid}` → `UserWordDetailOut {..., translation, contexts:[{sentence, surface_form, created_at}]}`
- `DELETE /vocabulary/{uuid}` → 204
- `UserWordOut`: `uuid, word_uuid, lemma, language, part_of_speech, mastery_level, created_at`
- `mastery_level ∈ {NEW, LEARNING, REVIEW, MASTERED}`

### Вправи (`app/routers/exercises.py`)
- `GET /exercises/next?exercise_type=&language=` → `ExerciseOut` | **403** (email не підтверджено) | **404** (пул порожній / денний ліміт)
- `POST /exercises/{uuid}/attempt` `{answers, response_time_ms?, mistakes?, timed_out}` → `AttemptResultOut {result, is_correct, correct_answers, mastery_level?}`
- `POST /exercises/refill?exercise_type=&language=` → `{status:"queued", task_id}` (Celery) або `{status:"done", created}` (inline)
- `GET /exercises/refill/{task_id}` → `{status: pending|running|done|failed, created?}` (поллінг, ~180с ліміт)
- `GET /exercises/preferences`, `PUT /exercises/preferences` `{exercise_types:[...]}`
- `GET /exercises/quota` → `{unlimited, used, limit, remaining}` (пейвол)

`ExerciseOut`: `uuid, exercise_type, prompt, difficulty, payload, created_at`. Ключ-відповідь **ніколи не приходить** у payload.

**Payload'и 5 підтримуваних типів** (з `practice.js`):

| Тип | payload | answers у attempt |
|---|---|---|
| `FILL_IN_BLANKS` | `{text: "...___1___...", blanks:[{index, options[]}]}` | `{"1": слово, ...}` |
| `MULTIPLE_CHOICE` | `{word, options[]}` | `{"1": слово}` |
| `FLASHCARD` | `{sentence, surface_form, word, translation}` | `{"1": "know"｜"dont_know"}` (самооцінка, без грейду) |
| `MATCH_PAIRS` | `{pairs:[{id, word, translation}], visible, max_mistakes, time_limit}` | вся ігрова логіка на клієнті → `{mistakes, timed_out}` |
| `TYPING` | `{text: "...___1___...", length, hint}` | `{"1": введене}` |

`SUPPORTED_EXERCISE_TYPES` (сервер приймає лише ці): `FILL_IN_BLANKS, MULTIPLE_CHOICE, FLASHCARD, MATCH_PAIRS, TYPING`. Решта `ExerciseType` — заплановані, поки не використовуються.

**MATCH_PAIRS — клієнтська логіка раунду** (з `practice.js`, треба відтворити 1-в-1):
показуємо `visible` пар (за замовч. 4), дві колонки перемішані окремо; вирішена пара
зникає, нові докидаються по 2 **лише після кожних 2 вирішених** (щоб не лишалась
єдина очевидна відповідь); лічильник життів `max_mistakes` (за замовч. 3); таймер
`time_limit` (за замовч. 60с); вихід часу або перевищення помилок = кінець раунду;
у submit летять `mistakes` і `timed_out`.

### Review SM-2 (`app/routers/learning.py`)
- `GET /review/next?limit=` → `[DueWordOut {uuid, lemma, language, mastery_level, due_at, translation?}]`
- `POST /review/{uuid}` `{quality: 0..5}` → `ReviewResultOut {mastery_level, repetitions, interval_days, ease_factor, due_at}`

### Оплата (`app/routers/payments.py`)
- `GET /payments/plans` → `[PlanOut]`
- `POST /payments/checkout` `{plan_code}` → `{checkout_url}` (hosted Stripe — відкрити у браузері)
- `POST /payments/portal` → `{portal_url}` (hosted — керування/скасування)
- `GET /payments/subscription` → `{status, plan_code?, is_active, current_period_end?, cancel_at_period_end}`
- Веб використовує `plan_code = "premium_monthly"`.

### Dashboard
Окремого stats-ендпоінта **немає**. Веб рахує все на клієнті (`dashboard.js`):
`GET /vocabulary?limit=1000` (розподіл mastery + total), `GET /review/next?limit=100`
(скільки на повторення, «100+» якщо ≥100), `GET /exercises/quota`, `GET /payments/subscription`.
Мобільний робить так само; за потреби пізніше додамо `/stats` на бекенді.

### Мови (хардкод у `frontend/api.js`)
`uk, pl, en, de, es, fr, it, pt` (російська свідомо виключена). Перенести в Dart-константу.

---

## 3. Аутентифікація на клієнті (найтонше місце)

- Токени зберігати у **flutter_secure_storage** (Keychain / Keystore), не в SharedPreferences.
- Кожен запит: `Authorization: Bearer <access>`.
- На **401** → один refresh, повтор запиту. **Rotating refresh вимагає single-flight:**
  паралельні запити не повинні робити refresh кожен своїм токеном — інакше другий
  спалить уже витрачений і сервер розцінить це як крадіжку та розлогінить усе.
  Точний зразок — `tryRefresh()/doRefresh()` в `frontend/api.js`. Реалізувати як
  чергу в Dio-інтерсепторі (один Future refresh, усі чекають на нього).
- Refresh не вдався → чистимо токени, на екран логіну.

**Google Sign-In:** пакет `google_sign_in` дає `idToken` → `POST /auth/google`.
Потрібні OAuth client ID під Android і iOS + `serverClientId` (web client ID бекенду).

**Email verify / reset:** бекенд редіректить у веб. Мобільний варіант — показати
«перевірте пошту», а перехід за посиланням відкриває веб-сторінку. Deep-links —
опційне покращення пізніше.

---

## 4. Ризики й рішення до релізу

1. **iOS + Stripe:** Apple відхиляє продаж цифрової підписки через зовнішній Stripe
   Checkout — потрібен IAP/StoreKit, або в iOS-білді ховати покупки (лишити керування
   лише там, де вже підписані). Вирішити до подання в App Store. Android (Google Play)
   має схожі, але м'якші правила.
2. **Rotating refresh** — див. §3, single-flight обов'язковий.
3. **CORS** мобільних не стосується (нативний HTTP без Origin), але переконатися,
   що прод віддає API по HTTPS (`https://langup.piatek-magazyn.com/api`).
4. **MATCH_PAIRS** — найбільший окремий шматок UI (ігровий стан на клієнті).

---

## 5. Стек

Flutter (stable) · **Riverpod** (стан) · **Dio** (+ refresh-інтерсептор) ·
**flutter_secure_storage** · **go_router** · **google_sign_in** · **url_launcher**
(Stripe / verify) · **freezed** + **json_serializable** АБО згенерований OpenAPI-клієнт (§6).

---

## 6. OpenAPI → Dart (виграш)

FastAPI віддає `/openapi.json`. Замість ручного переписування Pydantic-схем —
генеруємо Dart-моделі й клієнт автоматично:

```bash
# схема з локального бекенду
curl http://localhost:8000/openapi.json -o openapi.json
# генерація dart-dio клієнта (потрібен Java + openapi-generator)
openapi-generator generate -i openapi.json -g dart-dio -o packages/langup_api
```

Плюси: моделі завжди синхронні з бекендом, менше ручних помилок. Дрібні
специфічні payload'и вправ (динамічний `dict`) все одно обробляємо вручну.

---

## 7. Поетапний план

**Фаза 0 — Фундамент.** Новий репозиторій `langup_mobile`; `flutter create`; згенерований
Dart-клієнт з `/openapi.json`; Dio + rotating-refresh single-flight; secure storage;
go_router; конфіг оточень (dev/prod base URL); тема. Бекенд: Google client IDs під Android/iOS.

**Фаза 1 — Auth + оболонка.** Email/пароль, Google, forgot/reset, `/auth/me`, гейт рідної
мови, bottom-nav оболонка. Кінець фази — робочий залогінений застосунок.

**Фаза 2 — Словник.** Список (пагінація, пошук, фільтр мови), деталь (переклад + речення),
видалення, ручне додавання (`POST /vocabulary`), share-sheet capture.

**Фаза 3 — Практика (5 типів).** Ядро й найбільший обсяг: перемикачі типу/мови,
`next`/`attempt`, refill з поллінгом, стани quota/paywall, гейт «підтвердьте email».
MATCH_PAIRS — окремий підетап.

**Фаза 4 — Review (SM-2).** Черга `review/next`, картки, оцінка 0–5.

**Фаза 5 — Dashboard.** Розподіл mastery, плитки, статус плану (клієнтський розрахунок).

**Фаза 6 — Профіль + оплата.** Редагування профілю, підписка, upgrade/manage через
hosted Stripe (з урахуванням iOS-ризику), logout / logout-all.

**Фаза 7 — Поліш і реліз.** Офлайн/помилки, push (є заготовка `services/notifications`),
аналітика, публікація в сторах.

---

## 8. Зміни на бекенді (мінімальні, переважно адитивні)

- Google OAuth client ID під Android/iOS (конфіг + Google Cloud Console).
- (Опційно) deep-link-дружній редірект для verify/reset email.
- (Опційно) окремий `GET /api/stats` замість `/vocabulary?limit=1000` на дашборді.
- Переконатися, що прод API доступний по HTTPS ззовні.

Ядро API вже повне — мобільний застосунок здебільшого лише споживає наявні ендпоінти.
