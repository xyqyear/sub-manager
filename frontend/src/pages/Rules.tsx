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
import type { Breakpoint } from "antd";
import type { RuleSource, RuleSourceListItem } from "@/types/api";
import api, { errorDetail } from "@/utils/api";
import { formatRelativeTime } from "@/utils/time";
import { downloadTextFile } from "@/utils/download";
import useIsMobile from "@/hooks/useIsMobile";

type RuleFormValues = {
  name: string;
  mode: "remote" | "manual";
  behavior: "classical" | "domain" | "ipcidr";
  enabled: boolean;
  remote_url?: string;
  auto_update?: boolean;
  update_interval_sec?: number;
  payload_lines_text?: string;
};

const defaultFormValues: RuleFormValues = {
  name: "",
  mode: "remote",
  behavior: "domain",
  enabled: true,
  remote_url: "",
  auto_update: false,
  update_interval_sec: 86400,
  payload_lines_text: "",
};

function linesTextToArray(text: string | undefined): string[] {
  if (!text) {
    return [];
  }
  return text
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line.length > 0);
}

export default function RulesPage() {
  const isMobile = useIsMobile();
  const [items, setItems] = useState<RuleSourceListItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<RuleSourceListItem | null>(null);
  const [form] = Form.useForm<RuleFormValues>();
  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewContent, setPreviewContent] = useState("");
  const [previewTitle, setPreviewTitle] = useState("");

  const mode = Form.useWatch("mode", form);
  const behavior = Form.useWatch("behavior", form);

  const behaviorPlaceholders: Record<string, string> = {
    classical: [
      "DOMAIN-SUFFIX,google.com",
      "DOMAIN-KEYWORD,google",
      "DOMAIN,ad.com",
      "SRC-IP-CIDR,192.168.1.201/32",
      "IP-CIDR,127.0.0.0/8",
      "GEOIP,CN",
      "DST-PORT,80",
      "SRC-PORT,7777",
      "IP-CIDR,1.1.1.1/32,no-resolve",
    ].join("\n"),
    domain: [
      ".google.com",
      "+.youtube.com",
      "*.github.com",
      "example.com",
      "",
      "Wildcards:",
      "*  matches one level only (*.a.com -> b.a.com, not c.b.a.com)",
      "+  matches like DOMAIN-SUFFIX (+.a.com -> b.a.com and c.b.a.com and a.com)",
      ".  matches subdomains only (.a.com -> b.a.com and c.b.a.com, not a.com)",
    ].join("\n"),
    ipcidr: ["192.168.1.0/24", "10.0.0.1/32"].join("\n"),
  };

  const fetchItems = async () => {
    setLoading(true);
    try {
      const response = await api.get<RuleSourceListItem[]>("/admin/rules");
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

  const openEdit = async (item: RuleSourceListItem) => {
    if (item.mode === "manual") {
      try {
        const response = await api.get<RuleSource>(`/admin/rules/${item.id}`);
        const full = response.data;
        setEditing(item);
        form.setFieldsValue({
          name: full.name,
          mode: full.mode,
          behavior: full.behavior,
          enabled: full.enabled,
          remote_url: full.remote_url ?? "",
          auto_update: full.auto_update,
          update_interval_sec: full.update_interval_sec,
          payload_lines_text: (full.cached_payload_lines_json ?? []).join("\n"),
        });
        setOpen(true);
      } catch (error) {
        void message.error(errorDetail(error));
      }
      return;
    }
    setEditing(item);
    form.setFieldsValue({
      name: item.name,
      mode: item.mode,
      behavior: item.behavior,
      enabled: item.enabled,
      remote_url: item.remote_url ?? "",
      auto_update: item.auto_update,
      update_interval_sec: item.update_interval_sec,
      payload_lines_text: "",
    });
    setOpen(true);
  };

  const handleDelete = async (item: RuleSourceListItem) => {
    try {
      await api.delete(`/admin/rules/${item.id}`);
      void message.success("Deleted");
      await fetchItems();
    } catch (error) {
      void message.error(errorDetail(error));
    }
  };

  const handleRefresh = async (item: RuleSourceListItem) => {
    try {
      await api.post(`/admin/rules/${item.id}/refresh`);
      void message.success("Refreshed");
      await fetchItems();
    } catch (error) {
      void message.error(errorDetail(error));
    }
  };

  const hasCachedPayload = (item: RuleSourceListItem) =>
    item.cached_payload_lines_count != null && item.cached_payload_lines_count > 0;

  const payloadToText = (item: RuleSource) =>
    yaml.dump({ payload: item.cached_payload_lines_json }, { lineWidth: -1 });

  const fetchFullItem = async (id: string): Promise<RuleSource> => {
    const response = await api.get<RuleSource>(`/admin/rules/${id}`);
    return response.data;
  };

  const openPreview = async (item: RuleSourceListItem) => {
    try {
      const full = await fetchFullItem(item.id);
      setPreviewContent(payloadToText(full));
      setPreviewTitle(`${item.name} — Rules`);
      setPreviewOpen(true);
    } catch (error) {
      void message.error(errorDetail(error));
    }
  };

  const handleDownload = async (item: RuleSourceListItem) => {
    try {
      const full = await fetchFullItem(item.id);
      downloadTextFile(payloadToText(full), `${item.name}_rules.yaml`, "application/x-yaml");
    } catch (error) {
      void message.error(errorDetail(error));
    }
  };

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      const payload: Record<string, unknown> = {
        name: values.name,
        mode: values.mode,
        behavior: values.behavior,
        enabled: values.enabled,
        remote_url: values.remote_url,
        auto_update: values.auto_update,
        update_interval_sec: values.update_interval_sec,
      };

      if (values.mode === "manual") {
        payload.payload_lines = linesTextToArray(values.payload_lines_text);
      }

      let savedId: string | null = null;
      let needsRefresh = false;

      if (editing) {
        await api.put(`/admin/rules/${editing.id}`, payload);
        savedId = editing.id;
        needsRefresh = values.mode === "remote" && values.remote_url !== editing.remote_url;
      } else {
        const res = await api.post<RuleSource>("/admin/rules", payload);
        savedId = res.data.id;
        needsRefresh = values.mode === "remote";
      }

      setOpen(false);
      await fetchItems();

      if (needsRefresh && savedId) {
        try {
          await api.post(`/admin/rules/${savedId}/refresh`);
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
      title: "Behavior",
      dataIndex: "behavior",
      key: "behavior",
      responsive: ["sm"] as Breakpoint[],
      render: (value: string) => <Tag color="blue">{value}</Tag>,
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
      render: (_: unknown, row: RuleSourceListItem) =>
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
      render: (_: unknown, row: RuleSourceListItem) =>
        row.next_refresh_at ? (
          <Tooltip title={new Date(row.next_refresh_at).toLocaleString()}>
            <Typography.Text type="secondary">{formatRelativeTime(row.next_refresh_at)}</Typography.Text>
          </Tooltip>
        ) : (
          <Typography.Text type="secondary">-</Typography.Text>
        ),
    },
    {
      title: "Actions",
      key: "actions",
      render: (_: unknown, row: RuleSourceListItem) => (
        <Space>
          <Tooltip title="Edit">
            <Button size="small" icon={<EditOutlined />} onClick={() => void openEdit(row)} />
          </Tooltip>
          <Tooltip title="Refresh">
            <Button size="small" icon={<SyncOutlined />} onClick={() => void handleRefresh(row)} />
          </Tooltip>
          <Tooltip title="Preview">
            <Button size="small" icon={<EyeOutlined />} disabled={!hasCachedPayload(row)} onClick={() => void openPreview(row)} />
          </Tooltip>
          <Tooltip title="Download">
            <Button size="small" icon={<DownloadOutlined />} disabled={!hasCachedPayload(row)} onClick={() => void handleDownload(row)} />
          </Tooltip>
          <Popconfirm title="Delete rule?" onConfirm={() => void handleDelete(row)}>
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
        <Tooltip title="New Rule">
          <Button type="primary" icon={<PlusOutlined />} onClick={openCreate} />
        </Tooltip>
        <Tooltip title="Reload">
          <Button icon={<ReloadOutlined />} onClick={() => void fetchItems()} />
        </Tooltip>
      </Space>

      <Table<RuleSourceListItem>
        rowKey="id"
        loading={loading}
        dataSource={items}
        columns={columns}
        pagination={false}
        scroll={{ x: "max-content" }}
      />

      <Modal
        title={editing ? "Edit Rule" : "Create Rule"}
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

          <Form.Item name="behavior" label="Behavior" rules={[{ required: true }]}> 
            <Select
              options={[
                { label: "classical", value: "classical" },
                { label: "domain", value: "domain" },
                { label: "ipcidr", value: "ipcidr" },
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
              <Form.Item name="auto_update" label="Auto Update" valuePropName="checked">
                <Switch />
              </Form.Item>
              <Form.Item name="update_interval_sec" label="Update Interval (sec)">
                <InputNumber min={60} style={{ width: "100%" }} />
              </Form.Item>
            </>
          ) : (
            <Form.Item
              name="payload_lines_text"
              label="Payload Lines"
              rules={[{ required: true, message: "payload lines are required" }]}
            >
              <Input.TextArea
                rows={10}
                placeholder={behaviorPlaceholders[behavior] ?? behaviorPlaceholders.classical}
              />
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
