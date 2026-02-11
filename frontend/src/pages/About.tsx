import { Card, Descriptions } from "antd";

export default function AboutPage() {
  return (
    <Card title="Tech Stack">
      <Descriptions bordered column={1} size="middle">
        <Descriptions.Item label="Frontend">
          React + Vite + TypeScript + Ant Design 6
        </Descriptions.Item>
        <Descriptions.Item label="State and Utilities">
          Zustand + Axios + React Router
        </Descriptions.Item>
        <Descriptions.Item label="Backend">
          FastAPI + SQLAlchemy Async + aiosqlite
        </Descriptions.Item>
        <Descriptions.Item label="Python Tooling">
          uv + pytest + alembic
        </Descriptions.Item>
      </Descriptions>
    </Card>
  );
}
