import { Button, Card, Form, Input, Typography } from "antd";
import { useNavigate } from "react-router-dom";
import { getAdminToken, setAdminToken } from "@/utils/api";

interface LoginFormValues {
  token: string;
}

export default function LoginPage() {
  const navigate = useNavigate();

  const handleSubmit = (values: LoginFormValues) => {
    setAdminToken(values.token.trim());
    navigate("/subscriptions", { replace: true });
  };

  return (
    <div
      style={{
        minHeight: "100vh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: 24,
      }}
    >
      <Card title="Admin Login" style={{ width: 420 }}>
        <Typography.Paragraph type="secondary">
          Enter the configured admin bearer token.
        </Typography.Paragraph>
        <Form<LoginFormValues>
          layout="vertical"
          initialValues={{ token: getAdminToken() }}
          onFinish={handleSubmit}
        >
          <Form.Item
            label="Token"
            name="token"
            rules={[{ required: true, message: "Token is required" }]}
          >
            <Input.Password placeholder="change-me" />
          </Form.Item>

          <Button type="primary" htmlType="submit" block>
            Save and Continue
          </Button>
        </Form>
      </Card>
    </div>
  );
}
