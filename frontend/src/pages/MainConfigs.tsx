import {
  Button,
  Input,
  Modal,
  Popconfirm,
  Space,
  Table,
  Tag,
  Tooltip,
  Typography,
  message,
} from "antd";
import { CopyOutlined, DeleteOutlined, EditOutlined, EyeOutlined, PlusOutlined, ReloadOutlined } from "@ant-design/icons";
import { useEffect, useState } from "react";
import MainConfigEditorDrawer from "@/pages/main-configs/MainConfigEditorDrawer";
import type {
  MainConfig,
  PreviewResponse,
  RuleSource,
  SubscriptionSource,
} from "@/types/api";
import api from "@/utils/api";

export default function MainConfigsPage() {
  const [items, setItems] = useState<MainConfig[]>([]);
  const [subscriptions, setSubscriptions] = useState<SubscriptionSource[]>([]);
  const [rules, setRules] = useState<RuleSource[]>([]);
  const [loading, setLoading] = useState(false);
  const [editorOpen, setEditorOpen] = useState(false);
  const [editing, setEditing] = useState<MainConfig | null>(null);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewYaml, setPreviewYaml] = useState("");
  const [previewDiagnostics, setPreviewDiagnostics] =
    useState<PreviewResponse["diagnostics"] | null>(null);

  const fetchAll = async () => {
    setLoading(true);
    try {
      const [configsResponse, subscriptionsResponse, rulesResponse] = await Promise.all([
        api.get<MainConfig[]>("/admin/main-configs"),
        api.get<SubscriptionSource[]>("/admin/subscriptions"),
        api.get<RuleSource[]>("/admin/rules"),
      ]);

      setItems(configsResponse.data);
      setSubscriptions(subscriptionsResponse.data);
      setRules(rulesResponse.data);
    } catch (error) {
      void message.error(String(error));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void fetchAll();
  }, []);

  const openCreate = () => {
    setEditing(null);
    setEditorOpen(true);
  };

  const openEdit = (item: MainConfig) => {
    setEditing(item);
    setEditorOpen(true);
  };

  const closeEditor = () => {
    setEditorOpen(false);
    setEditing(null);
  };

  const handleDelete = async (item: MainConfig) => {
    try {
      await api.delete(`/admin/main-configs/${item.id}`);
      void message.success("Main config deleted");
      await fetchAll();
    } catch (error) {
      void message.error(String(error));
    }
  };

  const handlePreview = async (item: MainConfig) => {
    try {
      const response = await api.post<PreviewResponse>(`/admin/main-configs/${item.id}/preview`);
      setPreviewYaml(response.data.yaml);
      setPreviewDiagnostics(response.data.diagnostics);
      setPreviewOpen(true);
    } catch (error) {
      void message.error(String(error));
    }
  };

  const handleCopyArtifactLink = async (item: MainConfig) => {
    const link = `${window.location.origin}/api/public/configs/${item.id}/artifact?password=${encodeURIComponent(item.password_plain)}`;
    try {
      await navigator.clipboard.writeText(link);
      void message.success("Artifact URL copied");
    } catch {
      void message.error("Copy failed");
    }
  };

  const columns = [
    {
      title: "Name",
      dataIndex: "name",
      key: "name",
    },
    {
      title: "Final Target",
      key: "final_target",
      render: (_: unknown, row: MainConfig) => (
        <Tag color="blue">
          {row.final_target_type === "group"
            ? row.final_target_group_name ?? "group"
            : row.final_target_type}
        </Tag>
      ),
    },
    {
      title: "Enabled",
      dataIndex: "enabled",
      key: "enabled",
      render: (value: boolean) => (
        <Tag color={value ? "success" : "default"}>{value ? "on" : "off"}</Tag>
      ),
    },
    {
      title: "Actions",
      key: "actions",
      render: (_: unknown, row: MainConfig) => (
        <Space>
          <Tooltip title="Edit">
            <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(row)} />
          </Tooltip>
          <Tooltip title="Preview">
            <Button size="small" icon={<EyeOutlined />} onClick={() => void handlePreview(row)} />
          </Tooltip>
          <Tooltip title="Copy URL">
            <Button size="small" icon={<CopyOutlined />} onClick={() => void handleCopyArtifactLink(row)} />
          </Tooltip>
          <Popconfirm title="Delete this main config?" onConfirm={() => void handleDelete(row)}>
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
        <Tooltip title="New Main Config">
          <Button type="primary" icon={<PlusOutlined />} onClick={openCreate} />
        </Tooltip>
        <Tooltip title="Reload">
          <Button icon={<ReloadOutlined />} onClick={() => void fetchAll()} />
        </Tooltip>
      </Space>

      <Table<MainConfig>
        rowKey="id"
        loading={loading}
        dataSource={items}
        columns={columns}
        pagination={false}
      />

      <MainConfigEditorDrawer
        open={editorOpen}
        config={editing}
        subscriptions={subscriptions}
        rules={rules}
        onClose={closeEditor}
        onSaved={fetchAll}
      />

      <Modal
        title="Generated YAML Preview"
        open={previewOpen}
        onCancel={() => setPreviewOpen(false)}
        footer={null}
        width={1000}
        destroyOnHidden
      >
        {previewDiagnostics ? (
          <Space direction="vertical" style={{ display: "flex", marginBottom: 12 }}>
            <Typography.Text type="secondary">
              stale subscriptions:{" "}
              {previewDiagnostics.stale_subscription_ids.length
                ? previewDiagnostics.stale_subscription_ids.join(", ")
                : "none"}
            </Typography.Text>
            <Typography.Text type="secondary">
              stale rules:{" "}
              {previewDiagnostics.stale_rule_ids.length
                ? previewDiagnostics.stale_rule_ids.join(", ")
                : "none"}
            </Typography.Text>
            <Typography.Text type="secondary">
              warnings:{" "}
              {previewDiagnostics.warnings.length
                ? previewDiagnostics.warnings.join(" | ")
                : "none"}
            </Typography.Text>
          </Space>
        ) : null}
        <Input.TextArea
          value={previewYaml}
          rows={26}
          readOnly
          style={{ fontFamily: "monospace" }}
        />
      </Modal>
    </Space>
  );
}
