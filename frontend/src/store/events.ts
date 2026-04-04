import { defineStore } from 'pinia'
import {getMonthStartDates, formatDate} from '@/components/js/time-utils'
import { BASE_API_URL } from '@/config'
import { useAuthStore } from './auth'
import { useToastStore } from './toast'
import { ref } from 'vue'
import type { EventInput } from '@fullcalendar/core'
import {useTasksStore} from "@/store/tasks";

export const useEventsStore = defineStore('events', () => {
  const events = ref([] as Array<EventInput>)
  let fetchedKeys = [] as Array<string>
  const isSyncing = ref(false)

  const authStore = useAuthStore()
  const taskStore = useTasksStore()
  const toastStore = useToastStore()

  const adaptEventToFullCalendar = (event: any): EventInput => {
    return {
      id: event.id,
      title: event.summary || "No title",
      start: event.start.dateTime,
      end: event.end?.dateTime,
      backgroundColor: event.color,
      borderColor: event.color,
      googleEvent: event
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

    const syncToastId = toastStore.addToast('Syncing with Google Calendar 🔄', 0)

    try {
      const response = await fetch(
        `${BASE_API_URL}/events/sync/?start=${formatDate(startDate)}&end=${formatDate(endDate)}`,
        {
          method: 'POST',
          credentials: 'include',
          headers: {
            'Authorization': `JWT ${authStore.getAccessToken()}`
          }
        }
      )

      toastStore.removeToast(syncToastId)

      if (!response.ok) {
        toastStore.addToast('Failed to sync 😞', 4000)
      } else {
        const data = await response.json()

        for (const event of data) {
          const index = events.value.findIndex(e => e.id === event.id)

          if (index !== -1) {
            events.value[index] = adaptEventToFullCalendar(event)
          } else {
            events.value.push(adaptEventToFullCalendar(event))
          }
        }
      }
    } catch (error) {
      toastStore.removeToast(syncToastId)
      toastStore.addToast('Failed to sync 😞', 4000)
      console.error('Sync error:', error)
    } finally {
      isSyncing.value = false
    }
  }

  const getEvents = async (startDate: Date, endDate: Date) => {
    // Определяем какие месяцы нужно загрузить ДО запроса

    const monthsToFetch = getMonthStartDates(startDate, endDate)
      .filter(monthStart => !fetchedKeys.includes(monthStart))

    const result = await fetchEvents(startDate, endDate)
    const data: EventInput[] = await result.json()

    for (const event of data) {
      const alreadyExists = events.value.some(e => e.id === event.id)
      if (!alreadyExists) {
        events.value.push(adaptEventToFullCalendar(event))
      }
    }

    // Синхронизируем с Google после загрузки новых месяцев
    syncWithGoogle(startDate, endDate, monthsToFetch)

    return events.value
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

    const response = await fetch(`${BASE_API_URL}/events/from-task/`, {
      method: 'POST',
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `JWT ${authStore.getAccessToken()}`
      },
      body: JSON.stringify(data)
    })

    if (response.ok) {
      const event = await response.json()
      events.value.push(adaptEventToFullCalendar(event))

      const updatedTask = await taskStore.loadTaskById(task.id)
      task.events = updatedTask.events

      return event
    }
  }

  const getCalendarId = (eventId: string): number | undefined => {
    const event = events.value.find(event => event.id === eventId)
    const userCalendarId = event?.googleEvent?.user_calendar_id

    return userCalendarId? userCalendarId : undefined
  }

  const debounceMap = new Map<string, any>()

  interface eventUpdateData {
    id: string,
    newStart: string,
    newEnd: string,
    title?: string
  }

  const updateEvent = (data: eventUpdateData) => {
    const { id, newStart, newEnd, title } = data

    if (debounceMap.has(id)) {
      clearTimeout(debounceMap.get(id))
    }

    const timeout = setTimeout(async () => {
      debounceMap.delete(id) // Удаляем по завершении

      const calendarId = getCalendarId(id)

      console.log(calendarId)

      if (!calendarId) return

      const payload = {
        event_id: id,
        start: {
          dateTime: newStart,
        },
        end: {
          dateTime: newEnd,
        },
        user_calendar_id: calendarId
      }

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

    debounceMap.set(id, timeout)
  }

  const deleteEvent = async (eventId: string, userCalendarId: number) => {
    await fetch(`${BASE_API_URL}/events/`, {
      method: 'DELETE',
      credentials: 'include',
      headers: {
        'Authorization': `JWT ${authStore.getAccessToken()}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        event_id: eventId,
        user_calendar_id: userCalendarId
      })
    })
  }

  return {
    events,
    getEvents,
    createEvent,
    updateEvent,
    deleteEvent
  }
})
