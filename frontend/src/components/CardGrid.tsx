import { Col, Empty, Row, Spin } from "antd";
import type { ReactNode } from "react";
import SortableWrapper from "@/components/dnd/SortableWrapper";
import SortableItem from "@/components/dnd/SortableItem";

interface CardGridProps<T> {
  items: T[];
  loading: boolean;
  rowKey: (item: T) => string;
  renderCard: (item: T, dragHandle: ReactNode) => ReactNode;
  onReorder?: (oldIndex: number, newIndex: number) => void;
}

export default function CardGrid<T>({ items, loading, rowKey, renderCard, onReorder }: CardGridProps<T>) {
  const ids = items.map((item) => rowKey(item));

  const grid = (
    <Row gutter={[16, 16]}>
      {items.map((item) => {
        const key = rowKey(item);
        if (onReorder) {
          return (
            <Col key={key} xs={24} sm={24} md={12} lg={8} xl={8} xxl={6}>
              <SortableItem id={key}>
                {(dragHandle) => renderCard(item, dragHandle)}
              </SortableItem>
            </Col>
          );
        }
        return (
          <Col key={key} xs={24} sm={24} md={12} lg={8} xl={8} xxl={6}>
            {renderCard(item, null as unknown as ReactNode)}
          </Col>
        );
      })}
    </Row>
  );

  return (
    <Spin spinning={loading}>
      {items.length === 0 && !loading ? (
        <Empty />
      ) : onReorder ? (
        <SortableWrapper items={ids} onReorder={onReorder} strategy="rect">
          {grid}
        </SortableWrapper>
      ) : (
        grid
      )}
    </Spin>
  );
}
