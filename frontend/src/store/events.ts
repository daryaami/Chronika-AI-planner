import { defineStore } from 'pinia'
import {getMonthStartDates, formatDate} from '@/components/js/time-utils'
import { BASE_API_URL } from '@/config'
import { useAuthStore } from './auth'
import { useToastStore } from './toast'
import { ref } from 'vue'
import type { EventInput } from '@fullcalendar/core'
import {useTasksStore} from "@/store/tasks";

/** Стабильный ключ строки API (без изменения бэка): склейка при смене id после появления google_event_id */
function buildEventMergeKey(raw: Record<string, unknown>): string {
  const start = (raw.start as { dateTime?: string } | undefined)?.dateTime ?? ''
  const end = (raw.end as { dateTime?: string } | undefined)?.dateTime ?? ''
  const summary = String(raw.summary ?? '')
  const cal = raw.user_calendar_id != null ? String(raw.user_calendar_id) : ''
  const created = String(raw.created ?? '')
  return `${start}\x1e${end}\x1e${summary}\x1e${cal}\x1e${created}`
}

function hashStringToBase36(input: string): string {
  let hash = 2166136261
  for (let i = 0; i < input.length; i++) {
    hash ^= input.charCodeAt(i)
    hash = Math.imul(hash, 16777619) >>> 0
  }
  return hash.toString(36)
}

function findEventMergeIndex(list: EventInput[], adapted: EventInput): number {
  const key = (adapted.extendedProps as { event_merge_key?: string } | undefined)?.event_merge_key
  let i = list.findIndex((e) => e.id === adapted.id)
  if (i !== -1) return i
  if (key) {
    i = list.findIndex(
      (e) => (e.extendedProps as { event_merge_key?: string } | undefined)?.event_merge_key === key,
    )
  }
  return i
}

export const useEventsStore = defineStore('events', () => {
  const events = ref([] as Array<EventInput>)
  let fetchedKeys = [] as Array<string>
  /** Диапазон последней загрузки с планировщика — для точечного refetch после ассистента */
  let lastPlannerFetchRange: { start: Date; end: Date } | null = null
  const isSyncing = ref(false)

  const authStore = useAuthStore()
  const taskStore = useTasksStore()
  const toastStore = useToastStore()

  const adaptEventToFullCalendar = (event: any): EventInput => {
    const raw = event as Record<string, unknown>
    const mergeKey = buildEventMergeKey(raw)
    const googleId = raw.id != null && raw.id !== '' ? String(raw.id) : ''
    const id = googleId || `local:${hashStringToBase36(mergeKey)}`

    return {
      id,
      title: (event.summary as string) || 'Добавьте название',
      start: (event.start as { dateTime?: string } | undefined)?.dateTime,
      end: (event.end as { dateTime?: string } | undefined)?.dateTime,
      backgroundColor: event.color,
      borderColor: event.color,
      googleEvent: event,
      extendedProps: {
        user_calendar_id: event.user_calendar_id,
        event_merge_key: mergeKey,
      },
    }
  }

  const fetchEvents = async (startDate: Date, endDate: Date) => {
    const monthsToFetch = getMonthStartDates(startDate, endDate)
      .filter(monthStart => !fetchedKeys.includes(monthStart))

    if (monthsToFetch.length === 0) {
      return { json: async () => [] }
    }

    const fetchFn = () =>
      fetch(`${BASE_API_URL}/events/?start=${formatDate(startDate)}&end=${formatDate(endDate)}`, {
        method: 'GET',
        credentials: 'include',
        headers: {
          'Authorization': `JWT ${authStore.getAccessToken()}`
        }
      })

    const response = await authStore.ensureAuthorizedRequest(fetchFn)

    fetchedKeys = [...fetchedKeys, ...monthsToFetch]

    return response
  }

  // Синхронизация с Google Calendar
  const syncWithGoogle = async (startDate: Date, endDate: Date, monthsToFetch: string[]) => {
    // Если уже синхронизируем - не запускаем ещё раз
    if (isSyncing.value) return

    // Нет новых месяцев - не синхронизируем
    if (monthsToFetch.length === 0) return

    isSyncing.value = true

    const syncToastId = toastStore.addToast('Синхронизируем события с Google Calendar 🔄', 0)

    try {
      const fetchFn = () =>
        fetch(
          `${BASE_API_URL}/events/sync/?start=${formatDate(startDate)}&end=${formatDate(endDate)}`,
          {
            method: 'POST',
            credentials: 'include',
            headers: {
              'Authorization': `JWT ${authStore.getAccessToken()}`
            }
          }
        )

      const response = await authStore.ensureAuthorizedRequest(fetchFn)

      toastStore.removeToast(syncToastId)

      if (!response.ok) {
        toastStore.addToast('Ошибка синхронизации с Google Calendar 😞', 4000)
      } else {
        const data = await response.json()

        for (const event of data) {
          const adapted = adaptEventToFullCalendar(event)
          const index = findEventMergeIndex(events.value, adapted)
          if (index !== -1) {
            events.value.splice(index, 1, adapted)
          } else {
            events.value.push(adapted)
          }
        }
      }
    } catch (error) {
      toastStore.removeToast(syncToastId)
      toastStore.addToast('Ошибка синхронизации с Google Calendar 😞', 4000)
      console.error('Sync error:', error)
    } finally {
      isSyncing.value = false
    }
  }

  type GetEventsOptions = { skipGoogleSync?: boolean }

  const getEvents = async (
    startDate: Date,
    endDate: Date,
    opts: GetEventsOptions = {},
  ) => {
    // Определяем какие месяцы нужно загрузить ДО запроса

    const monthsToFetch = getMonthStartDates(startDate, endDate)
      .filter(monthStart => !fetchedKeys.includes(monthStart))

    const result = await fetchEvents(startDate, endDate)
    const data: EventInput[] = await result.json()

    for (const event of data) {
      const adapted = adaptEventToFullCalendar(event)
      const index = findEventMergeIndex(events.value, adapted)
      if (index !== -1) {
        events.value.splice(index, 1, adapted)
      } else {
        events.value.push(adapted)
      }
    }

    // После refetch только из БД (например ассистент) не дергаем Google — тост раздражает и лишний трафик
    if (!opts.skipGoogleSync) {
      syncWithGoogle(startDate, endDate, monthsToFetch).then()
    }

    return events.value
  }

  const setLastPlannerFetchRange = (startDate: Date, endDate: Date) => {
    lastPlannerFetchRange = {
      start: new Date(startDate),
      end: new Date(endDate),
    }
  }

  /**
   * Подтянуть события с GET без сброса fetchedKeys и без POST /events/sync/.
   * Сброс кэша месяцев гонялся с concurrent datesSet и снова вызывал синхронизацию с Google.
   */
  const refreshEventsFromLastPlannerRange = async () => {
    if (!lastPlannerFetchRange) return
    const { start, end } = lastPlannerFetchRange

    const fetchFn = () =>
      fetch(
        `${BASE_API_URL}/events/?start=${formatDate(start)}&end=${formatDate(end)}`,
        {
          method: 'GET',
          credentials: 'include',
          headers: {
            Authorization: `JWT ${authStore.getAccessToken()}`,
          },
        },
      )

    const response = await authStore.ensureAuthorizedRequest(fetchFn)
    if (!response.ok) return

    const data: unknown[] = await response.json()
    for (const raw of data) {
      const event = raw as Record<string, unknown>
      const adapted = adaptEventToFullCalendar(event)
      const index = findEventMergeIndex(events.value, adapted)
      if (index !== -1) {
        events.value.splice(index, 1, adapted)
      } else {
        events.value.push(adapted)
      }
    }
  }

  const createEvent = async (info: any) => {
    const task = taskStore.getTaskById(Number(info.draggedEl.dataset.taskId))

    if (!task) return

    const data = {
      task_id: task.id,
      start: info.event.start.toISOString(),
      end: info.event.end.toISOString(),
      user_calendar_id: task.user_calendar_id
    }

    const loadingToastId = toastStore.addToast('Создаём событие... ⏳', 0)

    const response = await fetch(`${BASE_API_URL}/events/from-task/`, {
      method: 'POST',
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `JWT ${authStore.getAccessToken()}`
      },
      body: JSON.stringify(data)
    })

    toastStore.removeToast(loadingToastId)

    if (response.ok) {
      const event = await response.json()
      events.value.push(adaptEventToFullCalendar(event))

      const updatedTask = await taskStore.loadTaskById(task.id)
      task.events = updatedTask.events

      return event
    }
  }

  const getCalendarId = (eventId: string): number | undefined => {
    const event = events.value.find(event => String(event.id) === String(eventId))
    const userCalendarId = event?.googleEvent?.user_calendar_id

    return userCalendarId? userCalendarId : undefined
  }

  const debounceMap = new Map<string, any>()

  interface eventUpdateData {
    id: string | number,
    newStart: string,
    newEnd: string,
    title?: string
  }

  const updateEvent = (data: eventUpdateData) => {
    const { id, newStart, newEnd, title } = data
    const key = String(id)


    if (debounceMap.has(key)) {
      clearTimeout(debounceMap.get(key))
    }

    const timeout = setTimeout(async () => {
      debounceMap.delete(key)

      const calendarId = getCalendarId(key)

      if (!calendarId) return

      const dbId = typeof id === 'number' ? id : Number(id)

      if (!Number.isFinite(dbId)) return

      const payload = {
        id: dbId,
        start: {
          dateTime: newStart,
        },
        end: {
          dateTime: newEnd,
        },
        user_calendar_id: calendarId
      }

      console.log(payload)

      await fetch(`${BASE_API_URL}/events/`, {
        method: 'PUT',
        credentials: 'include',
        headers: {
          'Authorization': `JWT ${authStore.getAccessToken()}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(payload)
      })
    }, 400)

    debounceMap.set(key, timeout)
  }

  const deleteEvent = async (eventId: string | number, userCalendarId: number) => {
    const dbId = typeof eventId === 'number' ? eventId : Number(eventId)
    if (!Number.isFinite(dbId)) return

    const response = await fetch(`${BASE_API_URL}/events/`, {
      method: 'DELETE',
      credentials: 'include',
      headers: {
        'Authorization': `JWT ${authStore.getAccessToken()}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        id: dbId,
        user_calendar_id: userCalendarId
      })
    })

    if (response.ok) {
      events.value = events.value.filter(e => String(e.id) !== String(eventId))
    }
  }

  const createEventFromForm = async (data: {
    summary: string
    user_calendar_id: number
    description?: string
    start: { dateTime: string }
    end: { dateTime: string }
  }) => {
    const loadingToastId = toastStore.addToast('Создаём событие... ⏳', 0)

    try {
      const fetchFn = () =>
        fetch(`${BASE_API_URL}/events/`, {
          method: 'POST',
          credentials: 'include',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `JWT ${authStore.getAccessToken()}`
          },
          body: JSON.stringify(data)
        })

      const response = await authStore.ensureAuthorizedRequest(fetchFn)

      toastStore.removeToast(loadingToastId)

      if (response.ok) {
        const event = await response.json()
        // Сохраняем user_calendar_id в событии для последующего удаления
        event.user_calendar_id = data.user_calendar_id

        events.value.push(adaptEventToFullCalendar(event))
        toastStore.addToast('Event created successfully! ✅', 3000)
        return event
      } else {
        toastStore.addToast('Failed to create event 😞', 4000)
      }
    } catch (error) {
      toastStore.removeToast(loadingToastId)
      toastStore.addToast('Failed to create event 😞', 4000)
      console.error('Create event error:', error)
    }
  }

  const updateEventFromForm = async (data: {
    id: number
    summary: string
    user_calendar_id: number
    description?: string
    start: { dateTime: string }
    end: { dateTime: string }
  }) => {
    const loadingToastId = toastStore.addToast('Обновляем событие... ⏳', 0)

    try {
      const fetchFn = () =>
        fetch(`${BASE_API_URL}/events/`, {
          method: 'PUT',
          credentials: 'include',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `JWT ${authStore.getAccessToken()}`
          },
          body: JSON.stringify(data)
        })

      const response = await authStore.ensureAuthorizedRequest(fetchFn)

      toastStore.removeToast(loadingToastId)

      if (response.ok) {
        const responseData = await response.json().catch(() => null)

        if (responseData) {
          events.value = events.value.map(event =>
            String(event.id) === String(data.id) ? adaptEventToFullCalendar(responseData) : event
          )
        } else {
          events.value = events.value.map(event => {
            if (String(event.id) !== String(data.id)) return event

            return {
              ...event,
              title: data.summary,
              start: data.start.dateTime,
              end: data.end.dateTime
            }
          })
        }

        toastStore.addToast('Event updated successfully! ✅', 3000)
        return responseData
      }

      toastStore.addToast('Failed to update event 😞', 4000)
    } catch (error) {
      toastStore.removeToast(loadingToastId)
      toastStore.addToast('Failed to update event 😞', 4000)
      console.error('Update event error:', error)
    }
  }

  return {
    events,
    getEvents,
    setLastPlannerFetchRange,
    refreshEventsFromLastPlannerRange,
    createEvent,
    createEventFromForm,
    updateEventFromForm,
    updateEvent,
    deleteEvent
  }
})
