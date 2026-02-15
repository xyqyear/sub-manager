import { Col, Empty, Row, Spin } from "antd";
import type { ReactNode } from "react";

interface CardGridProps<T> {
  items: T[];
  loading: boolean;
  rowKey: (item: T) => string;
  renderCard: (item: T) => ReactNode;
}

export default function CardGrid<T>({ items, loading, rowKey, renderCard }: CardGridProps<T>) {
  return (
    <Spin spinning={loading}>
      {items.length === 0 && !loading ? (
        <Empty />
      ) : (
        <Row gutter={[16, 16]}>
          {items.map((item) => (
            <Col key={rowKey(item)} xs={24} sm={24} md={12} lg={8} xl={8} xxl={6}>
              {renderCard(item)}
            </Col>
          ))}
        </Row>
      )}
    </Spin>
  );
}
