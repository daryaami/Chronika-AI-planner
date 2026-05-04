interface ChatMessageBlock {
  type: 'text' | 'entity',
  text?: string,
  entity_type?: 'event',
  context_id?: string,
  fields?: {
    duration?: number,
    start_time?: string,
    end_time?: string,
    summary?: string,
    start?: string,
    end?: string,
    calendar_id?: number | string
  },
  mode?: 'editable' | 'readonly',
}

export interface ChatMessageType {
  message_id: string;
  role: 'user' | 'assistant';
  content: string;
  created_at?: Date,
  blocks?: ChatMessageBlock[]
}
