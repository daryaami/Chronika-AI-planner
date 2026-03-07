import {ref} from "vue";
import {useAuthStore} from "@/store/auth";
import {BASE_API_URL} from "@/config";
import {Calendar} from "@/types/calendar";

export const useCalendarsStore = () => {
  const calendars = ref<Calendar[]>([])
  const authStore = useAuthStore();

  const fetchCalendars = async () => {

    const fetchFn = () =>
      fetch(`${BASE_API_URL}/events/calendars/`, {
        method: 'GET',
        credentials: 'include',
        headers: {
          'Authorization': `JWT ${authStore.getAccessToken()}`
        }
      })

    const response = await authStore.ensureAuthorizedRequest(fetchFn)
    calendars.value = await response.json()
  }

  const getCalendars = async () => {

    if (!calendars.value.length) {
      await fetchCalendars();
    }

    return calendars.value
  }

  const getCalendarById = async (id: number) => {
    if (!calendars.value) {
      await fetchCalendars();
    }

    return calendars.value.find(calendar => calendar.id === id)
  }

  const setUpdatedCalendars = async (payload: Calendar[]) => {
    const fetchFn = () =>
      fetch(`${BASE_API_URL}/events/calendars/update/`, {
        method: 'POST',
        credentials: 'include',
        headers: {
          'Authorization': `JWT ${authStore.getAccessToken()}`
        },
        body: JSON.stringify(payload)
      })

    const response = await authStore.ensureAuthorizedRequest(fetchFn)

    if (response.ok) {
      calendars.value = await response.json()
    }
  }


  return { getCalendars, getCalendarById, setUpdatedCalendars }
}
