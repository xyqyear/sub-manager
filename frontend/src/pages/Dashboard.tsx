import { Button, Card, List, Space, Tag, Typography } from "antd";
import { useCallback, useEffect, useState } from "react";
import api from "@/utils/api";

type HealthResponse = {
  status: string;
  time: string;
};

type Item = {
  id: number;
  name: string;
  done: boolean;
  created_at: string;
};

export default function DashboardPage() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [items, setItems] = useState<Item[]>([]);
  const [loading, setLoading] = useState(false);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [healthResponse, itemsResponse] = await Promise.all([
        api.get<HealthResponse>("/health"),
        api.get<Item[]>("/items"),
      ]);
      setHealth(healthResponse.data);
      setItems(itemsResponse.data);
    } finally {
      setLoading(false);
    }
  }, []);

  const createSampleItem = useCallback(async () => {
    await api.post<Item>("/items", {
      name: `Sample Item ${new Date().toISOString()}`,
      done: false,
    });
    await loadData();
  }, [loadData]);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  return (
    <Space direction="vertical" size={16} style={{ display: "flex" }}>
      <Card title="Backend Status" loading={loading}>
        <Space>
          <Tag color={health?.status === "ok" ? "success" : "default"}>
            {health?.status ?? "unknown"}
          </Tag>
          <Typography.Text type="secondary">
            {health?.time ?? "No response"}
          </Typography.Text>
        </Space>
      </Card>

      <Card
        title="Items (Async SQLAlchemy)"
        extra={<Button onClick={createSampleItem}>Create Sample</Button>}
        loading={loading}
      >
        <List
          dataSource={items}
          renderItem={(item) => (
            <List.Item key={item.id}>
              <Space>
                <Typography.Text>{item.name}</Typography.Text>
                <Tag color={item.done ? "success" : "default"}>
                  {item.done ? "Done" : "Pending"}
                </Tag>
              </Space>
            </List.Item>
          )}
        />
      </Card>
    </Space>
  );
}
