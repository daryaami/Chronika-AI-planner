interface ChatMessageBlock {
  type: 'text' | 'entity',
  text?: string,
  entity_type?: 'event',
  fields?: {
    duration?: number,
    start_time?: string,
    end_time?: string,
    summary?: string
  },
  mode?: 'editable',
}

export interface ChatMessageType {
  message_id: string;
  role: 'user' | 'assistant';
  content: string;
  created_at?: Date,
  blocks?: ChatMessageBlock[]
}
