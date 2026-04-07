export interface TaskEvent {
  id: number;
  google_event_id?: string | null;
  summary?: string | null;
  description?: string | null;
  start_time: string;   // ISO-строка (DateTime)
  end_time: string;     // ISO-строка (DateTime)
  created: string;      // readOnly
  updated: string;      // readOnly
  htmlLink?: string | null;
  organizer_email?: string | null;
}

export type TaskPriority = "NONE" | "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";

export interface Task {
  id: number;                // readOnly
  title: string;             // max 255
  priority: TaskPriority;
  category_id: number | null;  // x-nullable
  due_date?: string | null;  // ISO, x-nullable
  user_calendar_id: number;
  completed: boolean;
  created: string;           // readOnly
  updated: string;           // readOnly
  events: TaskEvent[];       // readOnly
  el: null | HTMLElement;
  duration?: number;
  notes?: string | null;
}

export type WithEl<T> = T & { el: Element | null };

// Конкретный UI-тип для этого компонента
export type UiTask = WithEl<Task>;

export interface TaskCreate {
  title: string;
  priority?: TaskPriority;
  category_id: number;
  due_date?: string;
  user_calendar_id?: number;
  duration?: number;
  notes?:string,
  completed?: boolean,
}
