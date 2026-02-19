import type { ReactNode } from "react";
import {
  DndContext,
  closestCenter,
  KeyboardSensor,
  PointerSensor,
  TouchSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
} from "@dnd-kit/core";
import {
  SortableContext,
  sortableKeyboardCoordinates,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import type { FormListFieldData } from "antd";
import SortableItem from "./SortableItem";

interface SortableFormListProps {
  fields: FormListFieldData[];
  move: (from: number, to: number) => void;
  onAfterMove?: () => void;
  idPrefix?: string;
  children: (field: FormListFieldData, index: number, dragHandle: ReactNode) => ReactNode;
}

export default function SortableFormList({
  fields,
  move,
  onAfterMove,
  idPrefix = "sfl",
  children,
}: SortableFormListProps) {
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 8 } }),
    useSensor(TouchSensor, { activationConstraint: { delay: 200, tolerance: 5 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  const itemIds = fields.map((f) => `${idPrefix}-${f.key}`);

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    if (!over || active.id === over.id) return;
    const oldIndex = itemIds.indexOf(String(active.id));
    const newIndex = itemIds.indexOf(String(over.id));
    if (oldIndex !== -1 && newIndex !== -1) {
      move(oldIndex, newIndex);
      onAfterMove?.();
    }
  };

  return (
    <DndContext
      sensors={sensors}
      collisionDetection={closestCenter}
      onDragEnd={handleDragEnd}
    >
      <SortableContext items={itemIds} strategy={verticalListSortingStrategy}>
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {fields.map((field, index) => (
            <SortableItem key={field.key} id={`${idPrefix}-${field.key}`}>
              {(dragHandle) => children(field, index, dragHandle)}
            </SortableItem>
          ))}
        </div>
      </SortableContext>
    </DndContext>
  );
}
