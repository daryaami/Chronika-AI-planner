interface ChatEntitySelectionItem {
  id?: number | string,
  entity_type?: 'task' | 'event',
  context_id?: string,
  title?: string,
  start?: string,
  end?: string,
}

interface ChatTimeSlotItem {
  start: string,
  end: string,
}

export interface AssistantMutationResultItem {
  type: 'task' | 'event'
  operation: 'created' | 'updated' | 'deleted'
  entity: Record<string, unknown>
}

export interface ChatMessageBlock {
  type: 'text' | 'entity' | 'entity_selection' | 'time_slot_selection',
  text?: string,
  entity_type?: 'event' | 'task',
  context_id?: string,
  editable_fields?: string[],
  fields?: {
    duration?: number,
    start_time?: string,
    end_time?: string,
    summary?: string,
    title?: string,
    start?: string,
    end?: string,
    calendar_id?: number | string,
    due_date?: string,
    priority?: string,
    category?: string
  },
  mode?: 'editable' | 'readonly',
  entities?: ChatEntitySelectionItem[],
  slots?: ChatTimeSlotItem[]
}

export interface ChatMessageType {
  message_id: string;
  role: 'user' | 'assistant';
  content: string;
  created_at?: Date,
  blocks?: ChatMessageBlock[]
  /** Публичное состояние FSM (например waiting_confirmation), с ответа API или истории */
  state?: string
  /** Мутации сущностей с бэка (поле `result` в POST /assistant/message|action) */
  result?: AssistantMutationResultItem[]
}
