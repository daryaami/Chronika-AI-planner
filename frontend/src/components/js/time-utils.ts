const getStartOfMonth = (date: Date): Date => {
  return new Date(date.getFullYear(), date.getMonth(), 1);
}

const getEndOfMonth = (date: Date): Date => {
  return new Date(date.getFullYear(), date.getMonth() + 1, 0);
}

// Возвращает массив дат начала каждого месяца в формате "YYYY-MM-DD" (например: "2026-02-06")
const getMonthStartDates = (start: Date, end: Date): string[] => {
  const result: string[] = [];

  const current = new Date(start.getFullYear(), start.getMonth(), 1);

  while (current <= end) {
    result.push(formatDate(current));
    current.setMonth(current.getMonth() + 1);
  }

  return result;
}

// Возвращает дату в формате "YYYY-MM-DD" (например: "2026-02-06")
const formatDate = (date: Date): string => {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}


const getTomorrow = (date: Date): Date => {
  const tomorrow = new Date(date.getTime());
  tomorrow.setDate(tomorrow.getDate() + 1);
  return tomorrow
}

const getCurrentWeekMonday = (date: Date): Date => {
  const dayOfWeek = date.getDay();
  const diff = (dayOfWeek === 0 ? -6 : 1) - dayOfWeek;
  const monday = new Date(date);
  monday.setDate(date.getDate() + diff);
  return monday;
}

const addMinutes = (date: Date, minutes: number): Date => {
  const copy = new Date(date) // чтобы не мутировать оригинал
  copy.setMinutes(copy.getMinutes() + minutes)
  return copy
}

// Возвращает дату в формате:
// - для дат текущей недели: "ddd, HH:mm" (например: "Thu, 14:30")
// - для остальных дат: "d MMMM" (например: "8 February")
const formatDueDate = (date: Date): string => {
  const now = new Date()

  // Находим начало и конец текущей недели
  const startOfWeek = new Date(now)
  startOfWeek.setDate(now.getDate() - now.getDay()) // воскресенье
  startOfWeek.setHours(0, 0, 0, 0)

  const endOfWeek = new Date(startOfWeek)
  endOfWeek.setDate(startOfWeek.getDate() + 6) // суббота
  endOfWeek.setHours(23, 59, 59, 999)

  if (date >= startOfWeek && date <= endOfWeek) {
    return date.toLocaleString("en-US", {
      weekday: "short",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false
    }).replace(",", "")
  } else {
    return date.toLocaleString("en-US", {
      day: "numeric",
      month: "long"
    })
  }
}

// Возвращает день недели и дату в формате "ddd, d MMM" (например: "Thu, 8 Aug")
const toWeekDayAndDate = (date: Date): string => {
  // Thu, 8 Aug

  return new Intl.DateTimeFormat("en-US", {
    weekday: "short",
    day: "numeric",
    month: "short",
  }).format(date);
}

// Возвращает месяц и год в формате "MMM YYYY" (например: "Nov 2023")
const getMonthAndYear = (date: Date): string => {
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    year: "numeric"
  }).format(date);
}

export {
  getStartOfMonth,
  getEndOfMonth,
  getMonthStartDates,
  formatDate,
  getTomorrow,
  getCurrentWeekMonday,
  addMinutes,
  formatDueDate,
  toWeekDayAndDate,
  getMonthAndYear
};
