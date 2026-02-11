import {
  Alert,
  Layout,
  Menu,
  Space,
  Tag,
  Typography,
} from "antd";
import { ErrorBoundary } from "react-error-boundary";
import {
  Link,
  Navigate,
  Route,
  Routes,
  useLocation,
} from "react-router-dom";
import AboutPage from "@/pages/About";
import DashboardPage from "@/pages/Dashboard";

const { Header, Content, Footer } = Layout;

function ErrorFallback() {
  return (
    <Layout style={{ minHeight: "100vh" }}>
      <Content style={{ padding: 24 }}>
        <Alert
          type="error"
          showIcon
          message="Application error"
          description="An unexpected error occurred in the frontend."
        />
      </Content>
    </Layout>
  );
}

function AppShell() {
  const location = useLocation();

  return (
    <Layout style={{ minHeight: "100vh" }}>
      <Header style={{ display: "flex", alignItems: "center", gap: 16 }}>
        <Typography.Title level={4} style={{ color: "#fff", margin: 0 }}>
          Sub Manager
        </Typography.Title>
        <Tag color="blue">React + FastAPI</Tag>
        <Menu
          mode="horizontal"
          theme="dark"
          selectedKeys={[location.pathname]}
          items={[
            { key: "/", label: <Link to="/">Dashboard</Link> },
            { key: "/about", label: <Link to="/about">About</Link> },
          ]}
          style={{ flex: 1, minWidth: 0, background: "transparent" }}
        />
      </Header>

      <Content style={{ padding: 24 }}>
        <Space direction="vertical" size={24} style={{ display: "flex" }}>
          <Routes>
            <Route path="/" element={<DashboardPage />} />
            <Route path="/about" element={<AboutPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </Space>
      </Content>

      <Footer style={{ textAlign: "center" }}>
        React + Vite + Ant Design 6 + FastAPI
      </Footer>
    </Layout>
  );
}

export default function App() {
  return (
    <ErrorBoundary FallbackComponent={ErrorFallback}>
      <AppShell />
    </ErrorBoundary>
  );
}
