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
import { DeleteOutlined, DownloadOutlined, EditOutlined, EyeOutlined, PlusOutlined, ReloadOutlined, SyncOutlined } from "@ant-design/icons";
import { useEffect, useState } from "react";
import yaml from "js-yaml";
import type { SubscriptionSource } from "@/types/api";
import api, { errorDetail } from "@/utils/api";
import { formatRelativeTime } from "@/utils/time";
import { downloadTextFile } from "@/utils/download";

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
  proxy_yaml_object_text: "",
};

export default function SubscriptionsPage() {
  const [items, setItems] = useState<SubscriptionSource[]>([]);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<SubscriptionSource | null>(null);
  const [form] = Form.useForm<SubscriptionFormValues>();
  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewContent, setPreviewContent] = useState("");
  const [previewTitle, setPreviewTitle] = useState("");

  const mode = Form.useWatch("mode", form);

  const fetchItems = async () => {
    setLoading(true);
    try {
      const response = await api.get<SubscriptionSource[]>("/admin/subscriptions");
      setItems(response.data);
    } catch (error) {
      void message.error(errorDetail(error));
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
      void message.error(errorDetail(error));
    }
  };

  const handleRefresh = async (item: SubscriptionSource) => {
    try {
      await api.post(`/admin/subscriptions/${item.id}/refresh`);
      void message.success("Refreshed");
      await fetchItems();
    } catch (error) {
      void message.error(errorDetail(error));
    }
  };

  const hasCachedProxies = (item: SubscriptionSource) =>
    item.cached_proxies_json != null && item.cached_proxies_json.length > 0;

  const proxiesToYaml = (item: SubscriptionSource) =>
    yaml.dump(item.cached_proxies_json, { lineWidth: -1 });

  const openPreview = (item: SubscriptionSource) => {
    setPreviewContent(proxiesToYaml(item));
    setPreviewTitle(`${item.name} — Proxies`);
    setPreviewOpen(true);
  };

  const handleDownload = (item: SubscriptionSource) => {
    downloadTextFile(proxiesToYaml(item), `${item.name}_proxies.yaml`, "application/x-yaml");
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
      void message.error(errorDetail(error));
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
      title: "Last Refresh",
      key: "last_refresh_at",
      render: (_: unknown, row: SubscriptionSource) =>
        row.last_refresh_at ? (
          <Tooltip title={new Date(row.last_refresh_at).toLocaleString()}>
            <Typography.Text type="secondary">{formatRelativeTime(row.last_refresh_at)}</Typography.Text>
          </Tooltip>
        ) : (
          <Typography.Text type="secondary">-</Typography.Text>
        ),
    },
    {
      title: "Next Refresh",
      key: "next_refresh_at",
      render: (_: unknown, row: SubscriptionSource) =>
        row.next_refresh_at ? (
          <Tooltip title={new Date(row.next_refresh_at).toLocaleString()}>
            <Typography.Text type="secondary">{formatRelativeTime(row.next_refresh_at)}</Typography.Text>
          </Tooltip>
        ) : (
          <Typography.Text type="secondary">-</Typography.Text>
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
          <Tooltip title="Preview">
            <Button size="small" icon={<EyeOutlined />} disabled={!hasCachedProxies(row)} onClick={() => openPreview(row)} />
          </Tooltip>
          <Tooltip title="Download">
            <Button size="small" icon={<DownloadOutlined />} disabled={!hasCachedProxies(row)} onClick={() => handleDownload(row)} />
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
              label="Proxy YAML List"
              rules={[{ required: true, message: "proxy_yaml_object_text is required" }]}
            >
              <Input.TextArea rows={10} placeholder={"- name: node-1\n  type: socks5\n  server: 1.1.1.1\n  port: 1080"} />
            </Form.Item>
          )}
        </Form>
      </Modal>

      <Modal
        title={previewTitle}
        open={previewOpen}
        onCancel={() => setPreviewOpen(false)}
        footer={null}
        width={800}
        destroyOnHidden
      >
        <Input.TextArea
          value={previewContent}
          readOnly
          autoSize={{ minRows: 10, maxRows: 30 }}
          style={{ fontFamily: "monospace" }}
        />
      </Modal>
    </Space>
  );
}
