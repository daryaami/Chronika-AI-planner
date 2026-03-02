# Полное руководство по работе с Docker

## 📋 Содержание
1. [Предварительные требования](#предварительные-требования)
2. [Первоначальная настройка](#первоначальная-настройка)
3. [Сборка и запуск](#сборка-и-запуск)
4. [Работа с контейнерами](#работа-с-контейнерами)
5. [Обновление кода](#обновление-кода)
6. [Отладка и логи](#отладка-и-логи)
7. [Остановка и очистка](#остановка-и-очистка)

---

## Предварительные требования

### Установка Docker
- **Docker Desktop** (Windows/Mac): https://www.docker.com/products/docker-desktop
- **Docker Engine + Docker Compose** (Linux): https://docs.docker.com/engine/install/

### Проверка установки
```bash
docker --version
docker-compose --version
```

---

## Первоначальная настройка

### 1. Подготовка переменных окружения

Создайте файл `chronika/.env.production` с необходимыми переменными:

```bash
# Перейдите в директорию проекта
cd D:\Documents\projects\chronikaAPI

# Создайте файл .env.production (если его нет)
```

**Обязательные переменные для backend:**
```env
DJANGO_ENV=production
SECRET_KEY=your-secret-key-here
DEBUG=False
ALLOWED_HOSTS=localhost,127.0.0.1
DATABASE_URL=sqlite:///db.sqlite3
# ... другие настройки
```

### 2. Структура проекта

```
chronikaAPI/
├── docker-compose.yml          # Конфигурация всех сервисов
├── chronika/
│   ├── Dockerfile              # Backend образ
│   ├── .env.production         # Переменные окружения
│   └── requirements.txt        # Python зависимости
├── frontend/
│   ├── Dockerfile              # Frontend сборка
│   └── package.json            # Node.js зависимости
└── nginx/
    └── nginx.conf              # Конфигурация Nginx
```

---

## Сборка и запуск

### 🚀 Первый запуск (полная сборка)

```bash
# 1. Сборка всех образов и запуск контейнеров
docker-compose up -d --build

# Команда делает:
# - Собирает образы для backend, frontend, nginx
# - Создает сеть appnet
# - Запускает все контейнеры в фоновом режиме (-d)
```

### ⚡ Быстрый запуск (если образы уже собраны)

```bash
# Просто запуск существующих контейнеров
docker-compose up -d
```

### 📦 Сборка без кэша (чистая сборка)

```bash
# Если нужно пересобрать все с нуля
docker-compose build --no-cache
docker-compose up -d
```

---

## Работа с контейнерами

### Просмотр статуса контейнеров

```bash
# Список всех контейнеров и их статус
docker-compose ps

# Или через docker
docker ps
```

**Ожидаемый результат:**
```
NAME                    STATUS          PORTS
chronikaapi-backend     Up (healthy)    
chronikaapi-frontend    Up              
chronikaapi-nginx       Up              0.0.0.0:80->80/tcp
```

### Проверка работоспособности

```bash
# Проверка backend healthcheck
curl http://localhost/api/health/

# Проверка через браузер
# Откройте: http://localhost
```

### Перезапуск контейнеров

```bash
# Перезапуск всех контейнеров
docker-compose restart

# Перезапуск конкретного сервиса
docker-compose restart backend
docker-compose restart frontend
docker-compose restart nginx
```

---

## Обновление кода

### 🔄 Обновление Backend (Django)

```bash
# Вариант 1: Пересборка и перезапуск
docker-compose up -d --build backend

# Вариант 2: Остановка, сборка, запуск
docker-compose stop backend
docker-compose build backend
docker-compose up -d backend
```

### 🎨 Обновление Frontend (Vue.js)

```bash
# Пересборка и перезапуск (автоматически копирует файлы в volume)
docker-compose up -d --build frontend

# Или с очисткой кэша
docker-compose build --no-cache frontend
docker-compose up -d frontend
```

**Примечание:** Frontend контейнер автоматически копирует собранные файлы в общий volume при запуске, откуда их читает nginx. Дополнительные скрипты не нужны.

### 🔧 Обновление Nginx конфигурации

```bash
# После изменения nginx/nginx.conf
docker-compose restart nginx

# Или пересоздать контейнер
docker-compose up -d --force-recreate nginx
```

### 📝 Обновление переменных окружения

```bash
# 1. Отредактируйте chronika/.env.production
# 2. Перезапустите backend
docker-compose restart backend
```

---

## Отладка и логи

### Просмотр логов

```bash
# Логи всех сервисов
docker-compose logs -f

# Логи конкретного сервиса
docker-compose logs -f backend
docker-compose logs -f frontend
docker-compose logs -f nginx

# Последние 50 строк логов
docker-compose logs --tail=50 backend

# Логи с временными метками
docker-compose logs -f --timestamps backend
```

### Вход в контейнер (для отладки)

```bash
# Вход в backend контейнер
docker exec -it chronikaapi-backend bash

# Внутри контейнера можно выполнить:
python manage.py shell
python manage.py migrate
python manage.py createsuperuser

# Вход в frontend контейнер
docker exec -it chronikaapi-frontend sh

# Вход в nginx контейнер
docker exec -it chronikaapi-nginx sh
```

### Проверка сетевого подключения

```bash
# Проверка сети Docker
docker network inspect chronikaapi_appnet

# Проверка подключения backend из nginx
docker exec chronikaapi-nginx wget -O- http://backend:8000/api/health/
```

### Проверка файлов в контейнере

```bash
# Просмотр файлов frontend
docker exec chronikaapi-frontend ls -la /app/dist

# Просмотр файлов backend
docker exec chronikaapi-backend ls -la /app
```

---

## Остановка и очистка

### Остановка контейнеров

```bash
# Остановка всех контейнеров (без удаления)
docker-compose stop

# Остановка конкретного сервиса
docker-compose stop backend
```

### Удаление контейнеров

```bash
# Остановка и удаление контейнеров
docker-compose down

# Удаление контейнеров и сетей
docker-compose down --remove-orphans
```

### Полная очистка

```bash
# Удаление контейнеров, сетей и volumes
docker-compose down -v

# Удаление образов
docker-compose down --rmi all

# Полная очистка (контейнеры + образы + volumes)
docker-compose down -v --rmi all
```

### Очистка Docker системы

```bash
# Удаление неиспользуемых образов
docker image prune -a

# Удаление неиспользуемых volumes
docker volume prune

# Полная очистка (осторожно!)
docker system prune -a --volumes
```

---

## Часто используемые команды

### Быстрые команды для разработки

```bash
# Полная пересборка и запуск
docker-compose down && docker-compose up -d --build

# Пересборка только измененного сервиса
docker-compose up -d --build backend

# Просмотр логов в реальном времени
docker-compose logs -f

# Проверка статуса
docker-compose ps

# Перезапуск после изменений
docker-compose restart
```

### Команды для production

```bash
# Сборка с тегами версий
docker-compose build --no-cache
docker tag chronikaapi-backend:latest chronikaapi-backend:v1.0.0

# Сохранение образов
docker save chronikaapi-backend:latest | gzip > backend.tar.gz

# Загрузка образов
docker load < backend.tar.gz
```

---

## Решение проблем

### Проблема: Контейнер не запускается

```bash
# 1. Проверьте логи
docker-compose logs backend

# 2. Проверьте статус
docker-compose ps

# 3. Попробуйте запустить вручную
docker-compose up backend  # без -d для просмотра вывода
```

### Проблема: Порт 80 занят

```bash
# Проверьте, что использует порт 80
netstat -ano | findstr :80  # Windows
lsof -i :80                  # Linux/Mac

# Измените порт в docker-compose.yml:
# ports:
#   - "8080:80"  # Используйте другой порт
```

### Проблема: Frontend не обновляется

```bash
# 1. Пересоберите frontend
docker-compose build --no-cache frontend
docker-compose up -d frontend

# 2. Перезапустите nginx
docker-compose restart nginx

# 3. Очистите кэш браузера (Ctrl+Shift+R)
```

### Проблема: Backend не подключается к БД

```bash
# 1. Проверьте .env.production
cat chronika/.env.production

# 2. Проверьте логи
docker-compose logs backend

# 3. Выполните миграции
docker exec chronikaapi-backend python manage.py migrate
```

### Проблема: Ошибки при сборке

```bash
# Очистите кэш и пересоберите
docker-compose build --no-cache --pull

# Удалите старые образы
docker-compose down --rmi all
docker-compose build
```

---

## Полезные алиасы (опционально)

Добавьте в `~/.bashrc` или `~/.zshrc`:

```bash
# Docker Compose алиасы
alias dcu='docker-compose up -d'
alias dcd='docker-compose down'
alias dcb='docker-compose build'
alias dcl='docker-compose logs -f'
alias dcp='docker-compose ps'
alias dcr='docker-compose restart'
```

---

## Архитектура сервисов

### Backend (Django)
- **Порт:** 8000 (внутренний)
- **Healthcheck:** `/api/health/`
- **WSGI:** Gunicorn с 4 workers
- **Переменные:** `chronika/.env.production`

### Frontend (Vue.js)
- **Сборка:** Multi-stage build в Docker
- **Результат:** Файлы в `/app/dist` внутри контейнера
- **Volume:** Общий volume `frontend_dist` для frontend и nginx
- **Автоматизация:** При запуске контейнер копирует файлы из `/app/dist` в volume
- **Монтирование:** Nginx читает из того же volume

### Nginx
- **Порт:** 80 (публичный)
- **Функции:**
  - Статические файлы frontend
  - Проксирование `/api/` → backend:8000
  - SPA роутинг

---

## Проверочный чеклист

После запуска проверьте:

- [ ] Все контейнеры запущены: `docker-compose ps`
- [ ] Backend здоров: `curl http://localhost/api/health/`
- [ ] Frontend доступен: `http://localhost`
- [ ] API работает: `curl http://localhost/api/users/ping/`
- [ ] Логи без ошибок: `docker-compose logs`

---

## Дополнительные ресурсы

- [Docker Documentation](https://docs.docker.com/)
- [Docker Compose Documentation](https://docs.docker.com/compose/)
- [Django в Docker](https://docs.docker.com/samples/django/)
- [Vue.js Deployment](https://vuejs.org/guide/scaling-up/deployment.html)
