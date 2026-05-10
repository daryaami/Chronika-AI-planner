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

interface ChatMessageBlock {
  type: 'text' | 'entity' | 'entity_selection' | 'time_slot_selection',
  text?: string,
  entity_type?: 'event' | 'task',
  context_id?: string,
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
}
