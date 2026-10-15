# Forma

Local Qwen3-VL document understanding is available through the modular provider engine. See [Mac setup and measured benchmark](docs/QWEN_LOCAL_ENGINE.md). Student PDFs use the existing secure upload and teacher-review flow; templates are optional and document interpretation assigns no grades. Cloud Qwen is implemented with paid inference disabled by default: see [budget controls and approval-gated deployment steps](docs/QWEN_BUDGET_AND_OPENROUTER.md). The legacy crop-based MVP is described below; its unmetered paid Gemini calls are paused under the strict budget policy.

Forma — локальное рабочее пространство для проверки рукописных решений по математике и физике. Сервис извлекает ответы из шаблонных областей, предлагает расшифровку и оценку по рубрике, а преподаватель проверяет и утверждает каждую работу. Оценки ИИ остаются предложениями и не попадают в финальный экспорт до одобрения учителем.

## Возможности MVP

- Задания из 2–3 вопросов с условиями, эталонными решениями и критериями.
- Печатный A4 portrait бланк с областями ответов или загрузка своего пустого PDF с настройкой прямоугольников.
- Нормализованные координаты областей и поворот страниц на 90°, 180° или 270°.
- Один PDF с работами: одна страница на одного анонимного ученика.
- Предпросмотр нарезанных областей, AI-предложения, расшифровка и отметки неопределённости.
- Ручное редактирование баллов и комментария, утверждение и повторное открытие проверки.
- SQLite для заданий и оценок, локальное хранение PDF и кропов, экспорт утверждённых оценок в CSV.
- Деморежим с примером по наклонной плоскости и синтетическими работами.

По умолчанию SQLite-база находится в `backend/forma.sqlite3`, а оригиналы и кропы — в `backend/storage/`. Оба ресурса остаются локальными между запусками.

Для приемлемых кропов сканы должны быть выровнены и выполнены по тому же бланку. MVP рассчитан на A4 portrait и не выполняет перспективную коррекцию фотографий. Не используйте произвольные снимки под углом без предварительного выравнивания. ArUco-маркеры и гомография остаются возможным расширением.

## Требования

- Python 3.11 или новее.
- Node.js 18 или новее.
- npm.

## Установка и запуск

Из корня проекта создайте локальное окружение Python и установите зависимости:

```bash
cp .env.example .env
python3 -m venv backend/.venv
backend/.venv/bin/pip install -r backend/requirements.txt
cd frontend
npm install
```

В `.env` можно оставить `DEMO_MODE=true` для локального знакомства с интерфейсом. Код Gemini сохранён, но платные вызовы без учёта стоимости приостановлены политикой бюджета; используйте локальный Qwen или явно разрешённый адаптер OpenRouter. Никогда не добавляйте настоящий ключ в репозиторий.

Запустите backend в первом окне терминала:

```bash
cd backend
../backend/.venv/bin/uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

Во втором окне из корня проекта запустите frontend:

```bash
cd frontend
npm run dev
```

Откройте <http://localhost:3000>. Документация FastAPI доступна по адресу <http://127.0.0.1:8000/docs>.

Чтобы остановить процессы разработки, нажмите `Ctrl+C` в обоих окнах.

## Первый рабочий сценарий

1. Откройте демозадание или создайте новое с 2–3 вопросами, эталонными решениями и критериями начисления баллов.
2. Настройте шаблон: оставьте печатные области или загрузите пустой PDF, проверьте и отрегулируйте прямоугольники. Сохраните шаблон и используйте его при печати работ.
3. Загрузите один PDF, где каждой странице соответствует одна работа. Проверьте предпросмотр кропов и подтвердите запуск оценки.
4. На экране проверки сравните оригинал, расшифровку и AI-предложения. Измените спорные критерии или комментарий и утвердите оценку. Неопределённые ответы требуют внимания преподавателя.
5. Откройте результаты и экспортируйте утверждённые оценки в CSV. Неутверждённые предложения не являются окончательными результатами.

Идентификаторы учеников назначаются автоматически (`Student 01`, `Student 02`, …); Forma не пытается устанавливать личность по почерку.

## Учебные порталы (демо)

`/teacher` и `/student` открывают демонстрационные порталы для курсов и потоков, заданий, отправок и опубликованных оценок. Данные PHY101 в них синтетические. Студенческий маршрут `/student` показывает enrollment по коду потока; teacher-портал позволяет создавать потоки, повторно использовать задание в другом потоке и публиковать только уже утверждённые оценки старого grading workflow.

Для начала можно открыть демо-поток PHY101-F26 как студент и посмотреть задания, а как преподаватель — прошлые потоки, архив и очередь сравнения. Сходство вычисляется локально по нормализованным текстовым токенам и совпадающим последовательностям; процент — доля сопоставленных токенов отправленного текста, а не вероятность нарушения. Результат требует оценки преподавателем и не изменяет балл автоматически. Архивная страница позволяет искать только извлечённый текст и метаданные.

Без настроенной `FORMA_AUTH_REQUIRED=true` локальный режим остаётся демонстрационным и не защищён от сетевого доступа. В production используйте аутентификацию учителя/учеников, ограничьте доступ к Cloudflare Worker и Render API, настройте сроки хранения и резервное копирование Neon/R2, а также согласуйте обработку данных с учреждением. Учетные данные и секреты должны храниться только в Render environment; `NEXT_PUBLIC_*` переменные доступны браузеру.

## Конфигурация

Настройки читаются из `.env` в корне проекта:

| Переменная | Назначение |
| --- | --- |
| `DEMO_MODE` | `true` включает локальный деморежим; значение в `.env.example` предназначено для первого запуска. |
| `FORMA_DEMO_MODE` | Если задана, переопределяет `DEMO_MODE`; для production укажите `false`. |
| `GEMINI_API_KEY` | Сохранён для совместимости; платные вызовы приостановлены политикой бюджета. |
| `GEMINI_MODEL` | Модель Gemini; по умолчанию `gemini-flash-lite-latest`. |
| `FRONTEND_ORIGIN` | Origin браузерного приложения, по умолчанию `http://localhost:3000`. |
| `FORMA_DATABASE_URL` | Необязательный URL PostgreSQL; без него используется локальная SQLite. Для Neon используйте URL с `sslmode=require`. |
| `FORMA_STORAGE_BACKEND` | `local` (по умолчанию) или `r2`. |
| `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET_NAME` | Приватные настройки Cloudflare R2; нужны только при `FORMA_STORAGE_BACKEND=r2`. |
| `FORMA_AUTH_REQUIRED` | `true` включает обязательную Bearer-аутентификацию API. В production должно быть `true`. |
| `FORMA_AUTH_SECRET` | Длинный случайный секрет подписи короткоживущих токенов. Храните только в backend environment. |
| `FORMA_TEACHER_USERNAME`, `FORMA_TEACHER_PASSWORD` | Учётные данные учителя, хранящиеся только в backend environment; пароль должен содержать не менее 12 символов. |
| `FORMA_STUDENT_CREDENTIALS_JSON` | JSON-словарь `student_id: password`; идентификаторы должны совпадать с `student_id` в зачислениях, пароли — не менее 12 символов. |

Groq API в текущем MVP не подключён. Не загружайте реальные ученические работы в деморежим или сторонние API без соответствующего согласия и проверки требований к обработке персональных данных.

## Развертывание

### FastAPI на Render + Neon + R2

1. Создайте базу Neon PostgreSQL, скопируйте connection string с TLS (`sslmode=require`) и сохраните его как `FORMA_DATABASE_URL` в приватных переменных Render.
2. Создайте приватный bucket R2 и API token с доступом только к этому bucket. В Render Blueprint (`render.yaml`) задайте account ID, access key, secret key и имя bucket; не добавляйте эти значения во frontend или репозиторий.
3. Создайте случайный `FORMA_AUTH_SECRET`, учётные данные учителя и JSON-словарь паролей учеников. `student_id` должен совпадать с идентификатором зачисления. Настройте `FRONTEND_ORIGIN` на точный HTTPS origin Cloudflare и `FORMA_DEMO_MODE=false`.
4. Подключите Render к репозиторию и примените `render.yaml`. Free-сервис может засыпать и медленно отвечать на первый запрос; его файловая система временная, поэтому для развертывания включены Neon и R2.

### Next.js на Cloudflare Workers

1. В `frontend` скопируйте `.env.example` в `.env.production` для локальной сборки либо задайте `NEXT_PUBLIC_API_URL` как build-time variable в Cloudflare CI. Значение — публичный HTTPS URL Render API; оно не является секретом.
2. Выполните `npm ci`, затем `npm run cf:preview`, чтобы проверить Worker-совместимость локально.
3. Настройте Cloudflare account/Worker и выполните `npm run cf:deploy` либо подключите Cloudflare Workers Builds. Worker использует OpenNext adapter; обычные `npm run dev` и `npm run build` для локальной разработки/проверки остаются доступны.

### Данные и миграция

Подключение Neon создаёт новую постоянную базу, но не переносит данные из `backend/forma.sqlite3`. Не удаляйте и не заменяйте исходную SQLite базу. Для переноса существующих данных нужен отдельный проверенный export/import с резервной копией и перенос файлов из `backend/storage/` в R2 с сохранением относительных object keys. Не направляйте production на SQLite: бесплатный Render не гарантирует сохранность локальных файлов между перезапусками.

## Проверки

Backend-тесты запускаются из папки `backend`:

```bash
.venv/bin/python -m pytest -q
```

Production-сборка frontend:

```bash
cd frontend
npm run build
```

Проверка TypeScript:

```bash
cd frontend
npx tsc --noEmit
```

Проверка Worker runtime:

```bash
cd frontend
npm run cf:preview
```

## Ограничения и безопасность использования

- Требуется один ученик на страницу и тот же макет бланка; произвольное автоматическое обнаружение ответов не выполняется.
- Загружаемый PDF ограничен 30 МБ и 50 страницами; для каждого листа Forma создаёт отдельный анонимный идентификатор и набор ответов.
- Кропы проверяйте перед оцениванием: поворот страницы доступен, автоматического выравнивания перспективы нет.
- AI может неверно прочитать почерк или ход решения. Оценка требует проверки и утверждения учителем.
- Очередь фоновой оценки работает внутри процесса backend; незавершённая обработка может прекратиться при его перезапуске.
- Локальный режим по умолчанию открыт и предназначен только для демонстрации. Для сетевого развертывания включите `FORMA_AUTH_REQUIRED=true` и задайте серверные credentials; политика хранения данных и резервного копирования всё равно должна быть настроена отдельно.
- Функциональность не заменяет профессиональное педагогическое решение и проверку применимых правил обработки данных.

## Persistent accounts and universal course documents

The new verified-account workflow uses private course ownership, enrollment codes,
HttpOnly browser sessions through a same-origin Next.js proxy, private course
materials and teacher-reviewed universal document grades. Existing demo and legacy
administrator routes are retained during migration.

See [the audited product plan](docs/PRODUCT_EVOLUTION_PLAN.md) and
[account migration/deployment instructions](docs/ACCOUNT_MIGRATION_AND_DEPLOYMENT.md).
Public registration defaults **off** until TLS SMTP is configured; no verification
bypass is provided. New account passwords are Argon2id hashes. Configure
`FORMA_BACKEND_URL` on the frontend Worker and the SMTP variables on Render.

Academic assignments accept PDF, DOCX and PPTX without a mandatory crop template.
Programming assignments additionally accept restricted UTF-8 sources/ZIPs for
static review. PPTX extraction has no visual rendering, and DOCX extraction has no
reliable page boundaries. Course assignment rows link to submitted documents and
a rubric review workspace. Review versions are retained; grades are visible to
students only after explicit teacher publication. Full-document AI interpretation
and evidence-based automatic grading remain planned phases.

Additional checks:

```bash
cd frontend
npm test
npx tsc --noEmit
```


## Phase 3: institutional roles and document understanding

Public registration creates students only. Approved teachers, school administrators
and platform administrators use explicit institution membership and operator
bootstrap. See [Phase 3 implementation and operator steps](docs/PHASE3_IMPLEMENTATION_REPORT.md).

Submitted documents can be interpreted without answer-crop templates. PostgreSQL
jobs persist across restart, resume while Render is awake, and use bounded provider adapters and deterministic extraction. Local Ollama and
explicitly budgeted OpenRouter are available; unmetered paid Gemini is paused. Teacher task-sheet questions require
approval; interpretation corrections preserve the original and do not publish
grades. The same-origin Cloudflare proxy retains `redirect: "manual"`.

### Universal rubric assessment

Problem sets, essays and lab reports share rubric evaluation and explicit teacher confirmation. Assessment defaults to local Ollama; explicitly configured OpenRouter reuses the strict budget ledger. See the [local cloud pilot and approval-gated smoke test](docs/CLOUD_QWEN_PILOT.md) and separate [staging plan](docs/CLOUD_QWEN_STAGING_PLAN.md). See [Phase 4 implementation, real examples, file support and rollout](docs/UNIVERSAL_ASSESSMENT_PHASE4.md). Suggestions never publish grades; unsupported formats/categories remain available for manual review.

The [Teacher Review Workspace guide](docs/TEACHER_REVIEW_WORKSPACE.md) covers the redesigned document/criteria interface, persisted drafts, explicit publication, verification and exact local commands using saved data without inference.
