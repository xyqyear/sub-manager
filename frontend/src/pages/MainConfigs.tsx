import {
  Button,
  Drawer,
  Form,
  Input,
  Modal,
  Popconfirm,
  Select,
  Space,
  Switch,
  Table,
  Tag,
  Typography,
  message,
} from "antd";
import { useEffect, useState } from "react";
import type { BuilderState, MainConfig, PreviewResponse } from "@/types/api";
import api from "@/utils/api";

type MainConfigFormValues = {
  name: string;
  password_plain: string;
  base_config_yaml: string;
  enabled: boolean;
  final_target_type: "DIRECT" | "REJECT" | "group";
  final_target_group_name?: string;
};

const defaultMainConfigValues: MainConfigFormValues = {
  name: "",
  password_plain: "",
  base_config_yaml: "mixed-port: 7890\nmode: rule\n",
  enabled: true,
  final_target_type: "DIRECT",
  final_target_group_name: "",
};

const defaultBuilderState: BuilderState = {
  subscription_links: [],
  filtered_groups: [],
  manual_groups: [],
  dialer_override_rules: [],
  shunt_bindings: [],
};

export default function MainConfigsPage() {
  const [items, setItems] = useState<MainConfig[]>([]);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<MainConfig | null>(null);
  const [builderOpen, setBuilderOpen] = useState(false);
  const [builderConfig, setBuilderConfig] = useState<MainConfig | null>(null);
  const [builderText, setBuilderText] = useState(JSON.stringify(defaultBuilderState, null, 2));
  const [previewYaml, setPreviewYaml] = useState("");
  const [previewOpen, setPreviewOpen] = useState(false);
  const [form] = Form.useForm<MainConfigFormValues>();

  const finalTargetType = Form.useWatch("final_target_type", form);

  const fetchItems = async () => {
    setLoading(true);
    try {
      const response = await api.get<MainConfig[]>("/admin/main-configs");
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
    form.setFieldsValue(defaultMainConfigValues);
    setOpen(true);
  };

  const openEdit = (item: MainConfig) => {
    setEditing(item);
    form.setFieldsValue({
      name: item.name,
      password_plain: item.password_plain,
      base_config_yaml: "",
      enabled: item.enabled,
      final_target_type: item.final_target_type,
      final_target_group_name: item.final_target_group_name ?? "",
    });
    setOpen(true);
  };

  const handleDelete = async (item: MainConfig) => {
    try {
      await api.delete(`/admin/main-configs/${item.id}`);
      void message.success("Deleted");
      await fetchItems();
    } catch (error) {
      void message.error(String(error));
    }
  };

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      if (editing) {
        const payload: Record<string, unknown> = {
          name: values.name,
          password_plain: values.password_plain,
          enabled: values.enabled,
          final_target_type: values.final_target_type,
          final_target_group_name:
            values.final_target_type === "group"
              ? values.final_target_group_name
              : null,
        };
        if (values.base_config_yaml.trim()) {
          payload.base_config_yaml = values.base_config_yaml;
        }
        await api.put(`/admin/main-configs/${editing.id}`, payload);
      } else {
        await api.post("/admin/main-configs", {
          ...values,
          final_target_group_name:
            values.final_target_type === "group"
              ? values.final_target_group_name
              : null,
        });
      }
      setOpen(false);
      await fetchItems();
      void message.success(editing ? "Updated" : "Created");
    } catch (error) {
      void message.error(String(error));
    }
  };

  const openBuilder = async (item: MainConfig) => {
    setBuilderConfig(item);
    setBuilderOpen(true);
    try {
      const response = await api.get<BuilderState>(`/admin/main-configs/${item.id}/builder`);
      setBuilderText(JSON.stringify(response.data, null, 2));
    } catch (error) {
      setBuilderText(JSON.stringify(defaultBuilderState, null, 2));
      void message.error(String(error));
    }
  };

  const handleSaveBuilder = async () => {
    if (!builderConfig) {
      return;
    }
    try {
      const parsed = JSON.parse(builderText) as BuilderState;
      await api.put(`/admin/main-configs/${builderConfig.id}/builder`, parsed);
      void message.success("Builder saved");
    } catch (error) {
      void message.error(String(error));
    }
  };

  const handlePreview = async () => {
    if (!builderConfig) {
      return;
    }
    try {
      const response = await api.post<PreviewResponse>(
        `/admin/main-configs/${builderConfig.id}/preview`,
      );
      setPreviewYaml(response.data.yaml);
      setPreviewOpen(true);
    } catch (error) {
      void message.error(String(error));
    }
  };

  const handleCopyArtifactLink = async () => {
    if (!builderConfig) {
      return;
    }
    const link = `${window.location.origin}/api/public/configs/${builderConfig.id}/artifact?password=${encodeURIComponent(builderConfig.password_plain)}`;
    try {
      await navigator.clipboard.writeText(link);
      void message.success("Artifact link copied");
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
      title: "Final",
      key: "final",
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
          <Button size="small" onClick={() => openEdit(row)}>
            Edit
          </Button>
          <Button size="small" onClick={() => void openBuilder(row)}>
            Builder
          </Button>
          <Popconfirm title="Delete config?" onConfirm={() => void handleDelete(row)}>
            <Button size="small" danger>
              Delete
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <Space direction="vertical" style={{ display: "flex" }} size={16}>
      <Space>
        <Button type="primary" onClick={openCreate}>
          New Main Config
        </Button>
        <Button onClick={() => void fetchItems()}>Reload</Button>
      </Space>

      <Table<MainConfig>
        rowKey="id"
        loading={loading}
        dataSource={items}
        columns={columns}
        pagination={false}
      />

      <Modal
        title={editing ? "Edit Main Config" : "Create Main Config"}
        open={open}
        onCancel={() => setOpen(false)}
        onOk={() => void handleSubmit()}
        width={760}
        destroyOnHidden
      >
        <Form form={form} layout="vertical" initialValues={defaultMainConfigValues}>
          <Form.Item name="name" label="Name" rules={[{ required: true }]}> 
            <Input />
          </Form.Item>

          <Form.Item
            name="password_plain"
            label="Config Password"
            rules={[{ required: true }]}
          >
            <Input.Password />
          </Form.Item>

          <Form.Item
            name="base_config_yaml"
            label="Base Config YAML"
            rules={editing ? [] : [{ required: true }]}
            extra={editing ? "Leave empty to keep current value." : undefined}
          >
            <Input.TextArea rows={10} />
          </Form.Item>

          <Form.Item name="enabled" label="Enabled" valuePropName="checked">
            <Switch />
          </Form.Item>

          <Form.Item name="final_target_type" label="Final Target Type" rules={[{ required: true }]}> 
            <Select
              options={[
                { label: "DIRECT", value: "DIRECT" },
                { label: "REJECT", value: "REJECT" },
                { label: "group", value: "group" },
              ]}
            />
          </Form.Item>

          {finalTargetType === "group" ? (
            <Form.Item
              name="final_target_group_name"
              label="Final Target Group Name"
              rules={[{ required: true }]}
            >
              <Input />
            </Form.Item>
          ) : null}
        </Form>
      </Modal>

      <Drawer
        title={builderConfig ? `Builder: ${builderConfig.name}` : "Builder"}
        open={builderOpen}
        onClose={() => setBuilderOpen(false)}
        width={900}
        extra={
          <Space>
            <Button onClick={() => void handleCopyArtifactLink()}>Copy Artifact URL</Button>
            <Button onClick={() => void handlePreview()}>Preview</Button>
            <Button type="primary" onClick={() => void handleSaveBuilder()}>
              Save Builder
            </Button>
          </Space>
        }
      >
        <Typography.Paragraph type="secondary">
          Builder JSON editor. Keep schema aligned with backend BuilderPayload.
        </Typography.Paragraph>
        <Input.TextArea
          value={builderText}
          onChange={(event) => setBuilderText(event.target.value)}
          rows={28}
          style={{ fontFamily: "monospace" }}
        />
      </Drawer>

      <Modal
        title="Generated YAML Preview"
        open={previewOpen}
        onCancel={() => setPreviewOpen(false)}
        footer={null}
        width={960}
      >
        <Input.TextArea value={previewYaml} rows={26} readOnly style={{ fontFamily: "monospace" }} />
      </Modal>
    </Space>
  );
}
