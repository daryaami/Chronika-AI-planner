# Отчет по оценке ассистента Chronika AI

- Дата генерации: `2026-05-07T16:57:24.254322Z`
- Пользователь: `daryaami10@gmail.com`
- Сценариев: `5`
- Длительность прогона: `38.714` с

## Общие метрики

- TSR: **60.0%**
- Intent Accuracy: **60.0%**
- Entity Resolution Accuracy: **100.0%**
- Avg Turns to Success: **1**
- Median Latency: **4.922 c**
- P95 Latency: **21.695 c**
- Disambiguation Rate: **0.0%**

## Разбивка по категориям

| Категория | N | TSR % | Intent % | Entity % | Avg Turns | Median RT, c | P95 RT, c | Disambiguation % |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| tasks | 5 | 60.0 | 60.0 | 100.0 | 1 | 4.922 | 21.695 | 0.0 |

## Детализация по сценариям

| ID | Категория | Успех | State | Turns | Time, c | Tools | Ошибки |
|---|---|---:|---|---:|---:|---|---|
| A01 | tasks | 1 | success | 1 | 2.925 | create_task | - |
| A02 | tasks | 1 | success | 1 | 3.403 | create_task | - |
| A03 | tasks | 1 | success | 1 | 4.922 | create_task | - |
| A04 | tasks | 0 | success | 1 | 21.695 | search_entities | expected_tool_not_found:update_task |
| A05 | tasks | 0 | success | 1 | 5.728 | search_entities | expected_tool_not_found:update_task |
