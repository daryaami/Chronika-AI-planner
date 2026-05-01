import {defineStore} from "pinia";
import {BASE_API_URL} from "@/config";
import {useAuthStore} from "@/store/auth"
import {ref} from "vue";
import {Task, TaskCreate} from "@/types/task";

export const useTasksStore = defineStore('tasks', () => {
  const tasks = ref<Task[]>([])
  let isInitialized = false;

  const authStore = useAuthStore()

  const fetchTasks = async () => {
    const fetchFn = () => fetch(`${BASE_API_URL}/tasks/`, {
        method: 'GET',
        credentials: 'include',
        headers: {
          'Authorization': `JWT ${authStore.getAccessToken()}`
        }
      })

    const response = await authStore.ensureAuthorizedRequest(fetchFn)
    tasks.value = await response.json() as Task[]
  }

  const getTasks = async (): Promise<Task[]> => {
    if (!isInitialized) {
      await fetchTasks()
      isInitialized = true
    }

    return tasks.value as Task[]
  }

  const createTask = async (payload: TaskCreate) => {
    await fetch(`${BASE_API_URL}/tasks/`, {
      method: 'POST',
      credentials: 'include',
      headers: {
        'Authorization': `JWT ${authStore.getAccessToken()}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(payload)
    })

    await fetchTasks()
  }

  const deleteTask = async (id: number) => {
    await fetch(`${BASE_API_URL}/tasks/${id}/`, {
      method: 'DELETE',
      credentials: 'include',
      headers: {
        'Authorization': `JWT ${authStore.getAccessToken()}`,
        'Content-Type': 'application/json'
      }
    })

    await fetchTasks()
  }

  const toggleCompletedDebounceMap = new Map<number, any>()

  const toggleCompleteTask = (id: number, isCompleted: boolean) => {
    if (toggleCompletedDebounceMap.has(id)) {
      clearTimeout(toggleCompletedDebounceMap.get(id))
    }

    const timeout = setTimeout(async () => {
      toggleCompletedDebounceMap.delete(id) // Удаляем по завершении

      await fetch(`${BASE_API_URL}/tasks/${id}/`, {
        method: 'PUT',
        credentials: 'include',
        headers: {
          'Authorization': `JWT ${authStore.getAccessToken()}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ completed: isCompleted })
      })

      await fetchTasks()
    }, 400)

    toggleCompletedDebounceMap.set(id, timeout)
  }

  const getTaskById = (id: number) => {
    return tasks.value.find(task => task.id === id)
  }

  const loadTaskById = async (id: number) => {
    const response = await fetch(`${BASE_API_URL}/tasks/${id}/`, {
      method: 'GET',
      credentials: 'include',
      headers: {
        'Authorization': `JWT ${authStore.getAccessToken()}`
      }
    })

    const task = await response.json()
    return task as Task
  }

  const updateTask = async (task: Task) => {
    await fetch(`${BASE_API_URL}/tasks/${task.id}/`, {
      method: 'PUT',
      credentials: 'include',
      headers: {
        'Authorization': `JWT ${authStore.getAccessToken()}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(task)
    })

    await fetchTasks()
  }

  return {
    tasks,
    fetchTasks,
    getTasks,
    createTask,
    deleteTask,
    getTaskById,
    toggleCompleteTask,
    updateTask,
    loadTaskById
  }
})
