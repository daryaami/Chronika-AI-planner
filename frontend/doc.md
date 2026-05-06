Ключевая идея:

# 1. Общая модель протокола

> фронт работает не с “текстом”, а с **UI-элементами, привязанными к конкретному сообщению и context_id**
>

---

## 🔹 Message (ответ ассистента)

Ассистент возвращает **массив UI-блоков**, а не одну строку:

```json
{
  "message_id": "m1",
  "state": "waiting_confirmation",
  "blocks": [...]
}
```

---

## 🔹 Типы блоков (главное API)

```json
type Block =
  | TextBlock
  | EntityBlock
  | EntitySelectionBlock
  | TimeSlotSelectionBlock
```

---

# 💬 2. Типы ответов ассистента

## 2.1 TextBlock

```json
{
  "type": "text",
  "text": "Задача создана. Подтвердить?"
}
```

---

## 2.2 EntityBlock (создание / редактирование)

Используется когда:

- создаём
- показываем
- редактируем

```json
{
  "type": "entity",
  "entity_type": "task",
  "context_id": "e1",
  "mode": "editable | readonly",
  "fields": {
    "title": "полить цветы",
    "due_date": "2026-04-20T18:00:00",
    "priority": "medium",
    "category": "home"
  }
  "editable_fields": ["title", "due_date"]
}
```

---

## 🔥 Важно

- `context_id` — ключ для связи с Action Plan
- `mode`:
    - `editable` — пользователь может менять
    - `readonly` — не может менять

---

## 2.3 EntitySelectionBlock (disambiguation)

```json
{
  "type": "entity_selection",
  "entities": [
    {
      "id": 42,
      "entity_type": "task | event",
      "context_id": "e1",
      "title": "полить цветы",
      "start": "...",
      "end": "..."
    },
    {
      "id": 43,
      "entity_type": "task | event",
      "context_id": "e2",
      "title": "полить цветы дома"
      "start": "...",
      "end": "..."
    }
  ]
}
```

---

## 2.4 TimeSlotSelectionBlock

```json
{
  "type": "time_slot_selection",
  "context_id": "a1",
  "slots": [
    {
      "start": "2026-04-19T10:00:00",
      "end": "2026-04-19T11:00:00"
    },
    {
      "start": "2026-04-19T14:00:00",
      "end": "2026-04-19T15:00:00"
    }
  ]
}
```

---

# 📤 3. Основной endpoint (чат)

## POST `/assistant/message`

### Вход

```json
{
  "message": "Запланируй встречу завтра",
  "client_context": {
    "message_id": "m_prev"
  }
}
```

- `message_id` — id последнего сообщения ассистента

---

### Выход

```json
{
  "message_id": "m2",
  "state": "waiting_confirmation",
  "blocks": [...]
}
```

---

# ⚡ 4. Второй endpoint (UI actions)

## POST `/assistant/action`

---

## 💡 Общая идея

> любое действие UI = событие над конкретным block + context_id
>

---

## 🔹 Вход

```json
{
  "message_id": "m2",
  "action": {
    "type": "entity_update | select_entity | select_time_slot | confirm | cancel",
    "payload": {}
  }
}
```

---

# 🔥 4.1 Entity Update (редактирование)

```json
{
  "type": "entity_update",
  "payload": {
    "context_id": "e1",
    "fields": {
      "title": "полить цветы и деревья",
      "due_date": "2026-04-21T18:00:00"
    }
  }
}
```

---

# 🔥 4.2 Выбор сущности

```json
{
  "type": "select_entity",
  "payload": {
    "context_ids": ["e1"]
  }
}
```

---

# 🔥 4.3 Выбор тайм-слота

```json
{
  "type": "select_time_slot",
  "payload": {
    "context_id": "a1",
    "slot": {
      "start": "...",
      "end": "..."
    }
  }
}
```

---

# 🔥 4.4 Confirm

```json
{
  "type": "confirm"
}
```

---

# 🔥 4.5 Cancel

```json
{
  "type": "cancel"
}
```

---

# 🧠 5. Связь с твоей архитектурой

## 🔹 Почему это работает

### 1. context_id = мост между UI и Action Plan

- `entity.context_id → entities[]`
- `action.context_id → actions[]`

---

### 2. UI → Reply Interpreter

Все события `/assistant/action` превращаются в:

```json
{
  "dialog_intent": "...",
  "actions": [...],
  "target_ids": [...]
}
```

---

### 3. FSM остаётся единственным контроллером

Фронт:

- не знает про состояния FSM
- просто рендерит blocks

Бэк:

- полностью управляет логикой

---

# ⚠️ 6. Важный edge case (твой вопрос)

> “Да, запланируй её на пятницу. И создай задачу…”
>

---

## ❗ Что происходит сейчас

Reply Interpreter вернёт:

```json
{
  "dialog_intent": "confirm",
  "actions": [...],
  "new_intent_candidate": {
    "raw": "создай задачу погулять..."
  }
}
```

---

## ✅ FSM корректное поведение:

1. применить patch
2. выполнить confirm
3. завершить текущий plan
4. отправить `new_intent_candidate` в Intent Parser
5. начать новый цикл

---

## 💡 Вывод

👉 система **НЕ ломается**, если:

- FSM обрабатывает new_intent после confirm
- нет параллельных plan’ов

---

# 🔒 7. Инварианты протокола (очень важно для диплома)

1. Любой UI-элемент имеет `context_id`
2. Все действия фронта адресные
3. Фронт не отправляет "сырые намерения" кроме message
4. Все UI-действия → Reply Interpreter
5. Action Plan никогда не редактируется напрямую фронтом

---

# 🚀 8. Что можно улучшить (важное замечание)

Ты почти идеально спроектировала систему, но есть один риск:

## ❗ Проблема

`message_id` сейчас — просто ссылка

---

## 💡 Лучше

Добавить `interaction_id`:

```json
{
  "interaction_id": "i1",
  "message_id": "m2"
}
```

---

### Почему это важно:

- один interaction = один lifecycle FSM
- защищает от гонок
- удобно для восстановления состояния

---

# 🏁 Итог

Ты фактически получила:

### ✔️ Чёткое разделение:

- chat → Intent Parser / Reply Interpreter
- action → строго FSM-driven patch

### ✔️ UI как проекция Action Plan

### ✔️ Протокол:

- детерминированный
- расширяемый
- идеально ложится в диплом

---

Если хочешь, дальше можно сделать **прямо UML sequence diagram этого протокола** или **OpenAPI спецификацию** — это будет очень сильный кусок для ВКР.