import { Button, Layout, Menu, Space, Tag, Tooltip, Typography } from "antd";
import { LogoutOutlined } from "@ant-design/icons";
import { ErrorBoundary } from "react-error-boundary";
import {
  Link,
  Navigate,
  Route,
  Routes,
  useLocation,
  useNavigate,
} from "react-router-dom";
import LoginPage from "@/pages/Login";
import MainConfigsPage from "@/pages/MainConfigs";
import RulesPage from "@/pages/Rules";
import SubscriptionsPage from "@/pages/Subscriptions";
import { clearAdminToken, getAdminToken } from "@/utils/api";

const { Header, Content, Footer } = Layout;

function isLoggedIn(): boolean {
  return getAdminToken().trim().length > 0;
}

function ErrorFallback() {
  return (
    <Layout style={{ minHeight: "100vh" }}>
      <Content style={{ padding: 24 }}>
        <Typography.Title level={4}>Application error</Typography.Title>
      </Content>
    </Layout>
  );
}

function ProtectedAppLayout() {
  const location = useLocation();
  const navigate = useNavigate();

  const doLogout = () => {
    clearAdminToken();
    navigate("/login", { replace: true });
  };

  if (!isLoggedIn()) {
    return <Navigate to="/login" replace />;
  }

  return (
    <Layout style={{ minHeight: "100vh" }}>
      <Header style={{ display: "flex", alignItems: "center", gap: 16 }}>
        <Typography.Title level={4} style={{ color: "#fff", margin: 0 }}>
          Sub Manager
        </Typography.Title>
        <Tag color="blue">Token Admin</Tag>
        <Menu
          mode="horizontal"
          theme="dark"
          selectedKeys={[location.pathname]}
          items={[
            { key: "/subscriptions", label: <Link to="/subscriptions">Subscriptions</Link> },
            { key: "/rules", label: <Link to="/rules">Rules</Link> },
            { key: "/configs", label: <Link to="/configs">Main Configs</Link> },
          ]}
          style={{ flex: 1, minWidth: 0, background: "transparent" }}
        />
        <Tooltip title="Logout">
          <Button size="small" icon={<LogoutOutlined />} onClick={doLogout} />
        </Tooltip>
      </Header>

      <Content style={{ padding: 24 }}>
        <Routes>
          <Route path="/subscriptions" element={<SubscriptionsPage />} />
          <Route path="/rules" element={<RulesPage />} />
          <Route path="/configs" element={<MainConfigsPage />} />
          <Route path="*" element={<Navigate to="/subscriptions" replace />} />
        </Routes>
      </Content>

      <Footer style={{ textAlign: "center" }}>
        <Space>
          <span>Sub Manager v1</span>
          <span>React + FastAPI</span>
        </Space>
      </Footer>
    </Layout>
  );
}

export default function App() {
  return (
    <ErrorBoundary FallbackComponent={ErrorFallback}>
      <Routes>
        <Route
          path="/login"
          element={isLoggedIn() ? <Navigate to="/subscriptions" replace /> : <LoginPage />}
        />
        <Route path="/*" element={<ProtectedAppLayout />} />
      </Routes>
    </ErrorBoundary>
  );
}
