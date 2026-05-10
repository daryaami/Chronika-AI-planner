import { useEventsStore } from '@/store/events'
import { useTasksStore } from '@/store/tasks'
import type { AssistantMutationResultItem } from '@/types/chat'

/**
 * После ответа ассистента с полем `result`: перезагрузить задачи и события в текущем окне планировщика.
 * Локальные правки массива не доходили до UI (watch без deep, кэш месяцев у events).
 */
export function applyAssistantMutationResults(raw: unknown) {
  if (!Array.isArray(raw) || raw.length === 0) return

  let hadTask = false
  let hadEvent = false

  for (const item of raw as AssistantMutationResultItem[]) {
    if (!item || typeof item !== 'object') continue
    if (item.type === 'task') hadTask = true
    if (item.type === 'event') hadEvent = true
  }

  const tasksStore = useTasksStore()
  const eventsStore = useEventsStore()

  if (hadTask) {
    void tasksStore.fetchTasks()
  }
  if (hadEvent) {
    void eventsStore.refreshEventsFromLastPlannerRange()
  }
}
