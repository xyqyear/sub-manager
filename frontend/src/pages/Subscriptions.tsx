import {
  Button,
  Form,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Progress,
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
import type { Breakpoint } from "antd";
import type { SubscriptionSource, SubscriptionSourceListItem } from "@/types/api";
import api, { errorDetail } from "@/utils/api";
import { formatBytes, TRAFFIC_COLORS } from "@/utils/format";
import { formatRelativeTime } from "@/utils/time";
import { downloadTextFile } from "@/utils/download";
import useIsMobile from "@/hooks/useIsMobile";

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
  update_interval_sec: 86400,
  proxy_yaml_object_text: "",
};

export default function SubscriptionsPage() {
  const isMobile = useIsMobile();
  const [items, setItems] = useState<SubscriptionSourceListItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<SubscriptionSourceListItem | null>(null);
  const [form] = Form.useForm<SubscriptionFormValues>();
  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewContent, setPreviewContent] = useState("");
  const [previewTitle, setPreviewTitle] = useState("");

  const mode = Form.useWatch("mode", form);

  const fetchItems = async () => {
    setLoading(true);
    try {
      const response = await api.get<SubscriptionSourceListItem[]>("/admin/subscriptions");
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

  const openEdit = async (item: SubscriptionSourceListItem) => {
    setEditing(item);
    let proxyText = "";
    if (item.mode === "manual") {
      try {
        const full = await fetchFullItem(item.id);
        proxyText = proxiesToYaml(full);
      } catch {
        void message.error("Failed to load existing proxy data");
      }
    }
    form.setFieldsValue({
      name: item.name,
      mode: item.mode,
      enabled: item.enabled,
      remote_url: item.remote_url ?? "",
      remote_auth_header: item.remote_auth_header ?? "",
      auto_update: item.auto_update,
      update_interval_sec: item.update_interval_sec,
      proxy_yaml_object_text: proxyText,
    });
    setOpen(true);
  };

  const handleDelete = async (item: SubscriptionSourceListItem) => {
    try {
      await api.delete(`/admin/subscriptions/${item.id}`);
      void message.success("Deleted");
      await fetchItems();
    } catch (error) {
      void message.error(errorDetail(error));
    }
  };

  const handleRefresh = async (item: SubscriptionSourceListItem) => {
    try {
      await api.post(`/admin/subscriptions/${item.id}/refresh`);
      void message.success("Refreshed");
      await fetchItems();
    } catch (error) {
      void message.error(errorDetail(error));
    }
  };

  const hasCachedProxies = (item: SubscriptionSourceListItem) =>
    item.cached_proxies_count != null && item.cached_proxies_count > 0;

  const proxiesToYaml = (item: SubscriptionSource) =>
    yaml.dump(item.cached_proxies_json, { lineWidth: -1 });

  const fetchFullItem = async (id: string): Promise<SubscriptionSource> => {
    const response = await api.get<SubscriptionSource>(`/admin/subscriptions/${id}`);
    return response.data;
  };

  const openPreview = async (item: SubscriptionSourceListItem) => {
    try {
      const full = await fetchFullItem(item.id);
      setPreviewContent(proxiesToYaml(full));
      setPreviewTitle(`${item.name} — Proxies`);
      setPreviewOpen(true);
    } catch (error) {
      void message.error(errorDetail(error));
    }
  };

  const handleDownload = async (item: SubscriptionSourceListItem) => {
    try {
      const full = await fetchFullItem(item.id);
      downloadTextFile(proxiesToYaml(full), `${item.name}_proxies.yaml`, "application/x-yaml");
    } catch (error) {
      void message.error(errorDetail(error));
    }
  };

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      let savedId: string | null = null;
      let needsRefresh = false;

      if (editing) {
        await api.put(`/admin/subscriptions/${editing.id}`, values);
        savedId = editing.id;
        needsRefresh = values.mode === "remote" && values.remote_url !== editing.remote_url;
      } else {
        const res = await api.post<SubscriptionSource>("/admin/subscriptions", values);
        savedId = res.data.id;
        needsRefresh = values.mode === "remote";
      }

      setOpen(false);
      await fetchItems();

      if (needsRefresh && savedId) {
        try {
          await api.post(`/admin/subscriptions/${savedId}/refresh`);
          await fetchItems();
          void message.success(editing ? "Updated & refreshed" : "Created & refreshed");
        } catch (refreshError) {
          void message.warning(`${editing ? "Updated" : "Created"}, but refresh failed: ${errorDetail(refreshError)}`);
        }
      } else {
        void message.success(editing ? "Updated" : "Created");
      }
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
      responsive: ["sm"] as Breakpoint[],
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
      responsive: ["md"] as Breakpoint[],
      render: (_: unknown, row: SubscriptionSourceListItem) =>
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
      responsive: ["md"] as Breakpoint[],
      render: (_: unknown, row: SubscriptionSourceListItem) =>
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
      width: 280,
      responsive: ["lg"] as Breakpoint[],
      render: (_: unknown, row: SubscriptionSourceListItem) => {
        const info = row.subscription_userinfo_json;
        if (!info || !info.total) return <Typography.Text type="secondary">-</Typography.Text>;

        const upload = info.upload ?? 0;
        const download = info.download ?? 0;
        const total = info.total;
        const uploadPct = Math.min((upload / total) * 100, 100);
        const totalUsedPct = Math.min(((upload + download) / total) * 100, 100);

        return (
          <div>
            <Progress
              percent={totalUsedPct}
              success={{ percent: uploadPct, strokeColor: TRAFFIC_COLORS.upload }}
              strokeColor={TRAFFIC_COLORS.download}
              showInfo={false}
              size={[undefined as unknown as number, 8]}
            />
            <div style={{ fontSize: 12, lineHeight: "18px" }}>
              <span style={{ color: TRAFFIC_COLORS.upload }}>U: {formatBytes(upload)}</span>
              {" / "}
              <span style={{ color: TRAFFIC_COLORS.download }}>D: {formatBytes(download)}</span>
              {" / "}
              <span>{formatBytes(total)}</span>
            </div>
            {info.expire ? (
              <div style={{ fontSize: 12, color: "#888" }}>
                Exp: {new Date(info.expire * 1000).toLocaleDateString("sv-SE")}
              </div>
            ) : null}
          </div>
        );
      },
    },
    {
      title: "Actions",
      key: "actions",
      render: (_: unknown, row: SubscriptionSourceListItem) => (
        <Space>
          <Tooltip title="Edit">
            <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(row)} />
          </Tooltip>
          <Tooltip title="Refresh">
            <Button size="small" icon={<SyncOutlined />} onClick={() => void handleRefresh(row)} />
          </Tooltip>
          <Tooltip title="Preview">
            <Button size="small" icon={<EyeOutlined />} disabled={!hasCachedProxies(row)} onClick={() => void openPreview(row)} />
          </Tooltip>
          <Tooltip title="Download">
            <Button size="small" icon={<DownloadOutlined />} disabled={!hasCachedProxies(row)} onClick={() => void handleDownload(row)} />
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

      <Table<SubscriptionSourceListItem>
        rowKey="id"
        loading={loading}
        dataSource={items}
        columns={columns}
        pagination={false}
        scroll={{ x: "max-content" }}
      />

      <Modal
        title={editing ? "Edit Subscription" : "Create Subscription"}
        open={open}
        onCancel={() => setOpen(false)}
        onOk={() => void handleSubmit()}
        width={isMobile ? "95vw" : 720}
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
        width={isMobile ? "95vw" : 800}
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
