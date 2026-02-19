import type { ReactNode } from "react";
import { useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import DragHandle from "./DragHandle";

interface SortableItemProps {
  id: string | number;
  children: (dragHandle: ReactNode) => ReactNode;
}

export default function SortableItem({ id, children }: SortableItemProps) {
  const {
    attributes,
    listeners,
    setNodeRef,
    setActivatorNodeRef,
    transform,
    transition,
  } = useSortable({ id });

  const style: React.CSSProperties = {
    transform: CSS.Transform.toString(transform),
    transition,
  };

  const dragHandle = (
    <DragHandle ref={setActivatorNodeRef} listeners={listeners} />
  );

  return (
    <div ref={setNodeRef} style={style} {...attributes}>
      {children(dragHandle)}
    </div>
  );
}
