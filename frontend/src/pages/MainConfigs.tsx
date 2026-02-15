import {
  Button,
  Card,
  Input,
  Modal,
  Popconfirm,
  Space,
  Tag,
  Tooltip,
  Typography,
  message,
} from "antd";
import { BlockOutlined, CopyOutlined, DeleteOutlined, EditOutlined, EyeOutlined, PlusOutlined, ReloadOutlined } from "@ant-design/icons";
import { useEffect, useState } from "react";
import MainConfigEditorDrawer from "@/pages/main-configs/MainConfigEditorDrawer";
import type {
  MainConfig,
  PreviewResponse,
  RouteTemplate,
  RuleSourceListItem,
  SubscriptionSourceListItem,
} from "@/types/api";
import api, { errorDetail } from "@/utils/api";
import useIsMobile from "@/hooks/useIsMobile";
import CardGrid from "@/components/CardGrid";

export default function MainConfigsPage() {
  const isMobile = useIsMobile();
  const [items, setItems] = useState<MainConfig[]>([]);
  const [subscriptions, setSubscriptions] = useState<SubscriptionSourceListItem[]>([]);
  const [rules, setRules] = useState<RuleSourceListItem[]>([]);
  const [routeTemplates, setRouteTemplates] = useState<RouteTemplate[]>([]);
  const [loading, setLoading] = useState(false);
  const [editorOpen, setEditorOpen] = useState(false);
  const [editing, setEditing] = useState<MainConfig | null>(null);
  const [editorMode, setEditorMode] = useState<"create" | "edit" | "duplicate">("create");
  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewYaml, setPreviewYaml] = useState("");
  const [previewDiagnostics, setPreviewDiagnostics] =
    useState<PreviewResponse["diagnostics"] | null>(null);

  const fetchAll = async () => {
    setLoading(true);
    try {
      const [configsResponse, subscriptionsResponse, rulesResponse, routeTemplatesResponse] = await Promise.all([
        api.get<MainConfig[]>("/admin/main-configs"),
        api.get<SubscriptionSourceListItem[]>("/admin/subscriptions"),
        api.get<RuleSourceListItem[]>("/admin/rules"),
        api.get<RouteTemplate[]>("/admin/route-templates"),
      ]);

      setItems(configsResponse.data);
      setSubscriptions(subscriptionsResponse.data);
      setRules(rulesResponse.data);
      setRouteTemplates(routeTemplatesResponse.data);
    } catch (error) {
      void message.error(errorDetail(error));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void fetchAll();
  }, []);

  const openCreate = () => {
    setEditing(null);
    setEditorMode("create");
    setEditorOpen(true);
  };

  const openEdit = (item: MainConfig) => {
    setEditing(item);
    setEditorMode("edit");
    setEditorOpen(true);
  };

  const openDuplicate = (item: MainConfig) => {
    setEditing(item);
    setEditorMode("duplicate");
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
      void message.error(errorDetail(error));
    }
  };

  const handlePreview = async (item: MainConfig) => {
    try {
      const response = await api.post<PreviewResponse>(`/admin/main-configs/${item.id}/preview`);
      setPreviewYaml(response.data.yaml);
      setPreviewDiagnostics(response.data.diagnostics);
      setPreviewOpen(true);
    } catch (error) {
      void message.error(errorDetail(error));
    }
  };

  const handleCopyArtifactLink = async (item: MainConfig) => {
    const link = `${window.location.origin}/api/public/configs/${item.id}/artifact`;
    try {
      await navigator.clipboard.writeText(link);
      void message.success("Artifact URL copied");
    } catch {
      void message.error("Copy failed");
    }
  };

  const renderCard = (item: MainConfig) => (
    <Card
      size="small"

      title={item.name}
      extra={
        <Space>
          <Tooltip title="Edit">
            <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(item)} />
          </Tooltip>
          <Tooltip title="Duplicate">
            <Button size="small" icon={<BlockOutlined />} onClick={() => openDuplicate(item)} />
          </Tooltip>
          <Tooltip title="Preview">
            <Button size="small" icon={<EyeOutlined />} onClick={() => void handlePreview(item)} />
          </Tooltip>
          <Tooltip title="Copy URL">
            <Button size="small" icon={<CopyOutlined />} onClick={() => void handleCopyArtifactLink(item)} />
          </Tooltip>
          <Popconfirm title="Delete this main config?" onConfirm={() => void handleDelete(item)}>
            <Tooltip title="Delete">
              <Button size="small" danger icon={<DeleteOutlined />} />
            </Tooltip>
          </Popconfirm>
        </Space>
      }
    >
      <Space wrap size={4}>
        <Tag color="blue">
          {item.final_target_type === "group"
            ? item.final_target_group_name ?? "group"
            : item.final_target_type}
        </Tag>
        <Tag color={item.enabled ? "success" : "default"}>{item.enabled ? "on" : "off"}</Tag>
      </Space>
    </Card>
  );

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

      <CardGrid items={items} loading={loading} rowKey={(item) => item.id} renderCard={renderCard} />

      <MainConfigEditorDrawer
        open={editorOpen}
        config={editing}
        mode={editorMode}
        subscriptions={subscriptions}
        rules={rules}
        routeTemplates={routeTemplates}
        onClose={closeEditor}
        onSaved={fetchAll}
      />

      <Modal
        title="Generated YAML Preview"
        open={previewOpen}
        onCancel={() => setPreviewOpen(false)}
        footer={null}
        width={isMobile ? "95vw" : 1000}
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
