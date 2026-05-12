import {SelectSmallOption} from "@/types/selectSmallOption";
import {TaskPriority} from "@/types/task";

const PRIORITIES: SelectSmallOption<TaskPriority | null>[] = [
  {
    value: 'NONE',
    label: "Без приоритета",
    icon: "flag",
    color: "inactive",
  },
  {
    value: "MEDIUM",
    label: "Среднее",
    icon: "flag",
    color: "medium",
  },
  {
    value: "HIGH",
    label: "Важное",
    icon: "flag",
    color: "high",
  },
];

export {PRIORITIES}
