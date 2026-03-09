import type { ReactNode } from "react";
import { Skeleton } from "@/components/ui/skeleton";
import SortableItem from "@/components/dnd/SortableItem";
import SortableWrapper from "@/components/dnd/SortableWrapper";

interface CardGridProps<T> {
  items: T[];
  loading: boolean;
  rowKey: (item: T) => string;
  renderCard: (item: T, dragHandle: ReactNode) => ReactNode;
  onReorder?: (oldIndex: number, newIndex: number) => void;
}

export default function CardGrid<T>({
  items,
  loading,
  rowKey,
  renderCard,
  onReorder,
}: CardGridProps<T>) {
  if (loading) {
    return (
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4 gap-4">
        {[1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-48 rounded-lg" />
        ))}
      </div>
    );
  }

  if (items.length === 0) {
    return (
      <div className="flex items-center justify-center py-16 text-muted-foreground">
        No items found
      </div>
    );
  }

  const ids = items.map(rowKey);

  if (onReorder) {
    return (
      <SortableWrapper items={ids} onReorder={onReorder} strategy="rect">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4 gap-4">
          {items.map((item) => (
            <SortableItem key={rowKey(item)} id={rowKey(item)}>
              {(dragHandle) => renderCard(item, dragHandle)}
            </SortableItem>
          ))}
        </div>
      </SortableWrapper>
    );
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4 gap-4">
      {items.map((item) => renderCard(item, null as unknown as ReactNode))}
    </div>
  );
}
