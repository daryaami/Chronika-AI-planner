# Backend Test Scenarios

Команда для запуска тестов:
```
py manage.py test google_auth users tasks events assistant
```

Краткая карта покрытых сценариев в текущих backend-тестах.

## Endpoints

- `GET /api/health/` (`health`)  
  - Не покрыт тестами.

- `GET /api/auth/google/redirect/` (`google_auth:google_auth_redirect`)  
  - Покрыто: успешный ответ с `auth_url`, передача `consent=true`.

- `POST /api/auth/google/callback/` (`google_auth:google_callback`)  
  - Покрыто:  
    - ошибка при отсутствии `code/state`;  
    - успешный callback для существующего пользователя (через моки);  
    - `403`, если создается новый пользователь без `refresh_token` Google.

- `GET /api/events/` (`calendar_events`)  
  - Покрыто:
    - чтение только из БД (без обращения к Google), фильтрация по выбранным календарям и диапазону дат;
    - `400`, если отсутствуют `start/end`;
    - `400`, если передан невалидный формат даты.

- `POST /api/events/sync/` (`sync_calendar_events`)  
  - Покрыто:  
    - синхронизация новых событий из Google в БД (через мок `get_all_events`);  
    - удаление отсутствующих в Google событий только в заданном диапазоне;
    - структурированный ответ об ошибке (`detail/code`) при `APIException` из сервиса.

- `GET /api/events/calendars/` (`google_calendars_list`)  
  - Покрыто: успешная выдача календарей текущего пользователя.

- `POST /api/events/calendars/update/` (`update_calendar`)  
  - Покрыто: пересоздание календарей и применение `selected` из payload.

- `POST /api/events/calendars/toggle-select/` (`toggle_calendar_select`)  
  - Покрыто: успешное переключение через сервис и возврат `selected`.

- `POST /api/events/from-task/` (`event_from_task`)  
  - Покрыто: создание события из задачи с локальным сохранением `Event.task`.

- `POST /api/events/` (`calendar_events`)  
  - Покрыто:
    - создание события и сохранение локальной записи `Event`;
    - `404` при попытке создать событие в чужом календаре;
    - `400` при невалидном payload.

- `PUT /api/events/` (`calendar_events`)  
  - Покрыто:
    - обновление события и синхронизация локальной записи `Event`;
    - `500`, если Google-сервис вернул ошибку.

- `DELETE /api/events/` (`calendar_events`)  
  - Покрыто: удаление события из локальной БД после вызова сервиса.

- `POST /api/users/refresh/` (`token_refresh`)  
  - Покрыто: `403`, если отсутствует `refresh_jwt` cookie.

- `GET /api/users/ping/` (`ping`)  
  - Покрыто: успешная проверка при валидных `refresh_jwt` cookie и `access_jwt`.

- `POST /api/users/logout/` (`logout`)  
  - Покрыто: `204` и удаление cookie `refresh_jwt`.

- `GET /api/users/profile/` (`profile`)  
  - Покрыто: возврат данных текущего пользователя.

- `PATCH /api/users/profile/` (`profile`)  
  - Покрыто:  
    - успешное обновление `name` и `time_zone`;  
    - ошибка валидации при невалидной `time_zone`.

- `DELETE /api/users/profile/` (`profile`)  
  - Покрыто: удаление аккаунта текущего пользователя.

- `GET /api/tasks/` (`task-list`)  
  - Покрыто: возвращаются только задачи текущего пользователя.

- `POST /api/tasks/` (`task-list`)  
  - Покрыто: при отсутствии `user_calendar_id` используется primary-календарь пользователя.

- `GET /api/tasks/{id}/` (`task-detail`)  
  - Покрыто: чужая задача недоступна (`404`).

- `PATCH /api/tasks/{id}/` (`task-detail`)  
  - Покрыто: обновление своей задачи.

- `DELETE /api/tasks/{id}/` (`task-detail`)  
  - Покрыто:
    - удаление своей задачи;
    - `404` при попытке удалить чужую задачу.

- `GET /api/tasks/categories/` (`category-list`)  
  - Покрыто: в выдаче есть default-категории + свои, нет чужих приватных.

- `POST /api/tasks/categories/` (`category-list`)  
  - Покрыто: создание категории для текущего пользователя.

- `GET /api/tasks/categories/{id}/` (`category-detail`)  
  - Покрыто:
    - получение своей категории;
    - `404` для чужой приватной категории.

- `PATCH /api/tasks/categories/{id}/` (`category-detail`)  
  - Покрыто: обновление своей категории.

- `DELETE /api/tasks/categories/{id}/` (`category-detail`)  
  - Покрыто: удаление своей категории.

## Services

- `events.services.GoogleCalendarService.get_all_events`  
  - Покрыто: корректно сохраняется `organizer_email` из Google payload.

- `events.services.GoogleCalendarService.sync_events_for_user`  
  - Покрыто косвенно через endpoint `POST /api/events/sync/` (создание и удаление событий в диапазоне).

- `events.services.GoogleCalendarService` (остальные методы: `get_google_calendars`, `create_user_calendars`, `toggle_calendar_select`, `create_event`, `update_event`, `delete_event`, и др.)  
  - Не покрыты отдельными unit-тестами.

- `google_auth.services.GoogleRawLoginFlowService` (`get_authorization_url`, `get_tokens`, `get_user_info`, `refresh_access_token`)  
  - Отдельных unit-тестов нет; покрытие сейчас только через API-тесты с моками в `google_auth.apis`.

- `google_auth.services` функции (`set_refresh_cookie`, `store_user_token`, `get_user_token`, `get_user_credentials`, `save_google_refresh_token`)  
  - Покрыто unit-тестами:
    - установка cookie refresh JWT;
    - сохранение/чтение access token из cache;
    - сохранение Google refresh token в БД;
    - сборка credentials из сохраненных токенов.

- `users.services.AuthService`  
  - Отдельных unit-тестов нет; используется косвенно в тестах `google_auth` через моки.

## Assistant tests

- `assistant.tests.unit.test_intent_parser`  
  - Покрыто:
    - успешный разбор валидного JSON-ответа LLM в `ParsedIntentResult`;
    - fallback в `other`, если LLM-клиент падает;
    - fallback в `other`, если ответ не JSON;
    - извлечение JSON из "шумного" ответа;
    - нормализация невалидных `intent/entity_type` и некорректных структур полей;
    - проверка `response_format={"type":"json_object"}`;
    - разбор списка `items` с сохранением порядка.

- `assistant.tests.unit.test_embeddings_model`  
  - Покрыто:
    - выбор источника модели (`EMBEDDINGS_MODEL_PATH` vs fallback на `EMBEDDINGS_MODEL_ID`);
    - корректная передача параметров в `SentenceTransformer` (`device`, `trust_remote_code`, `cache_folder`);
    - singleton-поведение провайдера (модель инициализируется один раз);
    - ошибка при отсутствии `sentence-transformers`;
    - `EMBEDDINGS_ENABLED=false`: модель не грузится, `encode()` возвращает пустой результат, выводится warning;
    - проксирование аргументов `encode()` и оборачивание ошибок кодирования.

- `assistant.tests.integration.test_llm_integration`  
  - Live-интеграция с Mistral (по умолчанию пропущено).
  - Условие запуска: `RUN_LLM_INTEGRATION=1` + `MISTRAL_API_KEY`.
  - Покрыто: базовые русскоязычные сценарии (`create`, `reschedule`, multi-intent) с выводом сырого/нормализованного ответа.

- `assistant.tests.integration.test_embeddings_semantic_similarity`  
  - Live-интеграция эмбеддингов (по умолчанию пропущено).
  - Условие запуска: `RUN_EMBEDDINGS_INTEGRATION=1`.
  - Покрыто:
    - кодирование набора задач и расчет cosine similarity matrix;
    - проверка, что для ключевых фраз ближайшие соседи — смысловые перефразы;
    - печать матрицы сходства в консоль для визуальной проверки.
