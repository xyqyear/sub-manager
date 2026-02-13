import {
  Button,
  Form,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Select,
  Space,
  Switch,
  Table,
  Tag,
  Tooltip,
  Typography,
  message,
} from "antd";
import { DeleteOutlined, EditOutlined, PlusOutlined, ReloadOutlined, SyncOutlined } from "@ant-design/icons";
import { useEffect, useState } from "react";
import type { SubscriptionSource } from "@/types/api";
import api from "@/utils/api";

type SubscriptionFormValues = {
  name: string;
  mode: "remote" | "manual";
  enabled: boolean;
  remote_url?: string;
  remote_auth_header?: string;
  auto_update?: boolean;
  update_interval_sec?: number;
  proxy_yaml_object_text?: string;
};

const defaultFormValues: SubscriptionFormValues = {
  name: "",
  mode: "remote",
  enabled: true,
  remote_url: "",
  remote_auth_header: "",
  auto_update: false,
  update_interval_sec: 3600,
  proxy_yaml_object_text: "name: node-1\ntype: socks5\nserver: 1.1.1.1\nport: 1080\n",
};

export default function SubscriptionsPage() {
  const [items, setItems] = useState<SubscriptionSource[]>([]);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<SubscriptionSource | null>(null);
  const [form] = Form.useForm<SubscriptionFormValues>();

  const mode = Form.useWatch("mode", form);

  const fetchItems = async () => {
    setLoading(true);
    try {
      const response = await api.get<SubscriptionSource[]>("/admin/subscriptions");
      setItems(response.data);
    } catch (error) {
      void message.error(String(error));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void fetchItems();
  }, []);

  const openCreate = () => {
    setEditing(null);
    form.setFieldsValue(defaultFormValues);
    setOpen(true);
  };

  const openEdit = (item: SubscriptionSource) => {
    setEditing(item);
    form.setFieldsValue({
      name: item.name,
      mode: item.mode,
      enabled: item.enabled,
      remote_url: item.remote_url ?? "",
      remote_auth_header: item.remote_auth_header ?? "",
      auto_update: item.auto_update,
      update_interval_sec: item.update_interval_sec,
      proxy_yaml_object_text: "",
    });
    setOpen(true);
  };

  const handleDelete = async (item: SubscriptionSource) => {
    try {
      await api.delete(`/admin/subscriptions/${item.id}`);
      void message.success("Deleted");
      await fetchItems();
    } catch (error) {
      void message.error(String(error));
    }
  };

  const handleRefresh = async (item: SubscriptionSource) => {
    try {
      await api.post(`/admin/subscriptions/${item.id}/refresh`);
      void message.success("Refreshed");
      await fetchItems();
    } catch (error) {
      void message.error(String(error));
    }
  };

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      if (editing) {
        await api.put(`/admin/subscriptions/${editing.id}`, values);
      } else {
        await api.post("/admin/subscriptions", values);
      }
      setOpen(false);
      await fetchItems();
      void message.success(editing ? "Updated" : "Created");
    } catch (error) {
      void message.error(String(error));
    }
  };

  const columns = [
    {
      title: "Name",
      dataIndex: "name",
      key: "name",
    },
    {
      title: "Mode",
      dataIndex: "mode",
      key: "mode",
      render: (value: string) => <Tag>{value}</Tag>,
    },
    {
      title: "Status",
      dataIndex: "last_status",
      key: "last_status",
      render: (value: string) => (
        <Tag color={value === "ok" ? "success" : value === "error" ? "error" : "default"}>{value}</Tag>
      ),
    },
    {
      title: "Update",
      key: "update",
      render: (_: unknown, row: SubscriptionSource) => (
        <Typography.Text type="secondary">
          {row.auto_update ? `${row.update_interval_sec}s` : "manual"}
        </Typography.Text>
      ),
    },
    {
      title: "Traffic",
      key: "traffic",
      render: (_: unknown, row: SubscriptionSource) => (
        <Typography.Text type="secondary">
          {row.subscription_userinfo_raw ?? "-"}
        </Typography.Text>
      ),
    },
    {
      title: "Actions",
      key: "actions",
      render: (_: unknown, row: SubscriptionSource) => (
        <Space>
          <Tooltip title="Edit">
            <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(row)} />
          </Tooltip>
          <Tooltip title="Refresh">
            <Button size="small" icon={<SyncOutlined />} onClick={() => void handleRefresh(row)} />
          </Tooltip>
          <Popconfirm
            title="Delete subscription?"
            onConfirm={() => void handleDelete(row)}
          >
            <Tooltip title="Delete">
              <Button size="small" danger icon={<DeleteOutlined />} />
            </Tooltip>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <Space direction="vertical" style={{ display: "flex" }} size={16}>
      <Space>
        <Tooltip title="New Subscription">
          <Button type="primary" icon={<PlusOutlined />} onClick={openCreate} />
        </Tooltip>
        <Tooltip title="Reload">
          <Button icon={<ReloadOutlined />} onClick={() => void fetchItems()} />
        </Tooltip>
      </Space>

      <Table<SubscriptionSource>
        rowKey="id"
        loading={loading}
        dataSource={items}
        columns={columns}
        pagination={false}
      />

      <Modal
        title={editing ? "Edit Subscription" : "Create Subscription"}
        open={open}
        onCancel={() => setOpen(false)}
        onOk={() => void handleSubmit()}
        width={720}
        destroyOnHidden
      >
        <Form form={form} layout="vertical" initialValues={defaultFormValues}>
          <Form.Item name="name" label="Name" rules={[{ required: true }]}> 
            <Input />
          </Form.Item>

          <Form.Item name="mode" label="Mode" rules={[{ required: true }]}> 
            <Select
              options={[
                { label: "Remote", value: "remote" },
                { label: "Manual", value: "manual" },
              ]}
            />
          </Form.Item>

          <Form.Item name="enabled" label="Enabled" valuePropName="checked">
            <Switch />
          </Form.Item>

          {mode === "remote" ? (
            <>
              <Form.Item
                name="remote_url"
                label="Remote URL"
                rules={[{ required: true, message: "remote_url is required" }]}
              >
                <Input />
              </Form.Item>
              <Form.Item name="remote_auth_header" label="Authorization Header">
                <Input placeholder="token xxxxxx" />
              </Form.Item>
              <Form.Item name="auto_update" label="Auto Update" valuePropName="checked">
                <Switch />
              </Form.Item>
              <Form.Item name="update_interval_sec" label="Update Interval (sec)">
                <InputNumber min={60} style={{ width: "100%" }} />
              </Form.Item>
            </>
          ) : (
            <Form.Item
              name="proxy_yaml_object_text"
              label="Proxy YAML Object"
              rules={[{ required: true, message: "proxy_yaml_object_text is required" }]}
            >
              <Input.TextArea rows={10} />
            </Form.Item>
          )}
        </Form>
      </Modal>
    </Space>
  );
}
