import {
  Button,
  Card,
  Col,
  Form,
  Input,
  Modal,
  Popconfirm,
  Row,
  Select,
  Space,
  Switch,
  Tooltip,
  Typography,
  message,
} from "antd";
import { DeleteOutlined, EditOutlined, PlusOutlined, ReloadOutlined } from "@ant-design/icons";
import { useEffect, useState } from "react";
import { arrayMove } from "@dnd-kit/sortable";
import type { RouteTemplate, RuleSourceListItem } from "@/types/api";
import api, { errorDetail } from "@/utils/api";
import useIsMobile from "@/hooks/useIsMobile";
import CardGrid from "@/components/CardGrid";
import SortableFormList from "@/components/dnd/SortableFormList";

type SlotFormValue = { name: string };
type BindingFormValue = {
  binding_name: string;
  rule_source_id: string;
  default_target: string;
  no_resolve: boolean;
};
type TemplateFormValues = {
  name: string;
  slots: SlotFormValue[];
  bindings: BindingFormValue[];
};

const defaultFormValues: TemplateFormValues = {
  name: "",
  slots: [],
  bindings: [],
};

export default function RouteTemplatesPage() {
  const isMobile = useIsMobile();
  const [items, setItems] = useState<RouteTemplate[]>([]);
  const [rules, setRules] = useState<RuleSourceListItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<RouteTemplate | null>(null);
  const [form] = Form.useForm<TemplateFormValues>();

  const slotsWatch = Form.useWatch("slots", form);

  const slotTargetOptions = [
    { label: "DIRECT", value: "DIRECT" },
    { label: "REJECT", value: "REJECT" },
    ...(slotsWatch ?? [])
      .filter((s) => s?.name)
      .map((s) => ({ label: s.name, value: s.name })),
  ];

  const fetchAll = async () => {
    setLoading(true);
    try {
      const [templatesRes, rulesRes] = await Promise.all([
        api.get<RouteTemplate[]>("/admin/route-templates"),
        api.get<RuleSourceListItem[]>("/admin/rules"),
      ]);
      setItems(templatesRes.data);
      setRules(rulesRes.data);
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
    form.setFieldsValue(defaultFormValues);
    setOpen(true);
  };

  const openEdit = (item: RouteTemplate) => {
    setEditing(item);
    form.setFieldsValue({
      name: item.name,
      slots: item.slots.map((s) => ({ name: s.name })),
      bindings: item.bindings.map((b) => ({
        binding_name: b.binding_name,
        rule_source_id: b.rule_source_id,
        default_target: b.default_target,
        no_resolve: b.no_resolve,
      })),
    });
    setOpen(true);
  };

  const handleDelete = async (item: RouteTemplate) => {
    try {
      await api.delete(`/admin/route-templates/${item.id}`);
      void message.success("Deleted");
      await fetchAll();
    } catch (error) {
      void message.error(errorDetail(error));
    }
  };

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      const payload = {
        name: values.name,
        slots: (values.slots ?? []).map((s, i) => ({ name: s.name, position: i + 1 })),
        bindings: (values.bindings ?? []).map((b, i) => ({
          position: i + 1,
          binding_name: b.binding_name?.trim() || (rules.find((r) => r.id === b.rule_source_id)?.name ?? ""),
          rule_source_id: b.rule_source_id,
          default_target: b.default_target,
          no_resolve: Boolean(b.no_resolve),
        })),
      };

      if (editing) {
        await api.put(`/admin/route-templates/${editing.id}`, payload);
      } else {
        await api.post("/admin/route-templates", payload);
      }

      setOpen(false);
      await fetchAll();
      void message.success(editing ? "Updated" : "Created");
    } catch (error) {
      if (error && typeof error === "object" && "errorFields" in error) {
        void message.error("Please fill in all required fields");
        return;
      }
      void message.error(errorDetail(error));
    }
  };

  const handleReorder = async (oldIndex: number, newIndex: number) => {
    const reordered = arrayMove(items, oldIndex, newIndex);
    setItems(reordered);
    try {
      await api.put("/admin/route-templates/reorder", {
        items: reordered.map((item, i) => ({ id: item.id, position: i })),
      });
    } catch (error) {
      void message.error(errorDetail(error));
      await fetchAll();
    }
  };

  const renderCard = (item: RouteTemplate, dragHandle: React.ReactNode) => (
    <Card
      size="small"

      title={item.name}
      extra={
        <Space>
          {dragHandle}
          <Tooltip title="Edit">
            <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(item)} />
          </Tooltip>
          <Popconfirm title="Delete this route template?" onConfirm={() => void handleDelete(item)}>
            <Tooltip title="Delete">
              <Button size="small" danger icon={<DeleteOutlined />} />
            </Tooltip>
          </Popconfirm>
        </Space>
      }
    >
      <Typography.Text type="secondary">
        {item.slots.length} slots &middot; {item.bindings.length} bindings
      </Typography.Text>
    </Card>
  );

  return (
    <Space direction="vertical" style={{ display: "flex" }} size={16}>
      <Space>
        <Tooltip title="New Route Template">
          <Button type="primary" icon={<PlusOutlined />} onClick={openCreate} />
        </Tooltip>
        <Tooltip title="Reload">
          <Button icon={<ReloadOutlined />} onClick={() => void fetchAll()} />
        </Tooltip>
      </Space>

      <CardGrid items={items} loading={loading} rowKey={(item) => item.id} renderCard={renderCard} onReorder={handleReorder} />

      <Modal
        title={editing ? "Edit Route Template" : "Create Route Template"}
        open={open}
        onCancel={() => setOpen(false)}
        onOk={() => void handleSubmit()}
        width={isMobile ? "95vw" : 900}
        destroyOnHidden
      >
        <Form form={form} layout="vertical" initialValues={defaultFormValues}>
          <Form.Item name="name" label="Name" rules={[{ required: true }]}>
            <Input />
          </Form.Item>

          <Form.List name="slots">
            {(fields, { add, remove, move }) => (
              <Space direction="vertical" style={{ display: "flex" }}>
                <strong>Slots</strong>
                <SortableFormList fields={fields} move={move} idPrefix="slot">
                  {(field, _index, dragHandle) => (
                    <Card size="small">
                      <Row gutter={12} align="middle">
                        <Col>{dragHandle}</Col>
                        <Col flex="auto">
                          <Form.Item name={[field.name, "name"]} label="Slot Name" rules={[{ required: true }]} style={{ marginBottom: 0 }}>
                            <Input />
                          </Form.Item>
                        </Col>
                        <Col>
                          <Tooltip title="Delete">
                            <Button danger icon={<DeleteOutlined />} onClick={() => remove(field.name)} />
                          </Tooltip>
                        </Col>
                      </Row>
                    </Card>
                  )}
                </SortableFormList>
                <Tooltip title="Add Slot">
                  <Button icon={<PlusOutlined />} onClick={() => add({ name: "" })} />
                </Tooltip>
              </Space>
            )}
          </Form.List>

          <div style={{ height: 16 }} />

          <Form.List name="bindings">
            {(fields, { add, remove, move }) => (
              <Space direction="vertical" style={{ display: "flex" }}>
                <strong>Bindings</strong>
                <SortableFormList fields={fields} move={move} idPrefix="binding">
                  {(field, _index, dragHandle) => (
                    <Card size="small">
                      <Row gutter={12}>
                        <Col xs={1} style={{ display: "flex", alignItems: "center" }}>{dragHandle}</Col>
                        <Col xs={23} sm={6}>
                          <Form.Item name={[field.name, "rule_source_id"]} label="Rule Source" rules={[{ required: true }]}>
                            <Select
                              options={rules.map((r) => ({ label: `${r.name} (${r.behavior})`, value: r.id }))}
                              showSearch
                            />
                          </Form.Item>
                        </Col>
                        <Col xs={24} sm={6}>
                          <Form.Item noStyle shouldUpdate>
                            {() => {
                              const ruleSourceId = form.getFieldValue(["bindings", field.name, "rule_source_id"]) as string | undefined;
                              const ruleName = rules.find((r) => r.id === ruleSourceId)?.name;
                              return (
                                <Form.Item name={[field.name, "binding_name"]} label="Binding Name">
                                  <Input placeholder={ruleName || "Same as rule source"} />
                                </Form.Item>
                              );
                            }}
                          </Form.Item>
                        </Col>
                        <Col xs={24} sm={5}>
                          <Form.Item name={[field.name, "default_target"]} label="Default Target" rules={[{ required: true }]}>
                            <Select options={slotTargetOptions} showSearch />
                          </Form.Item>
                        </Col>
                        <Col xs={12} sm={3}>
                          <Form.Item name={[field.name, "no_resolve"]} label="No Resolve" valuePropName="checked">
                            <Switch />
                          </Form.Item>
                        </Col>
                        <Col xs={12} sm={3}>
                          <Form.Item label=" ">
                            <Tooltip title="Delete">
                              <Button danger icon={<DeleteOutlined />} onClick={() => remove(field.name)} />
                            </Tooltip>
                          </Form.Item>
                        </Col>
                      </Row>
                    </Card>
                  )}
                </SortableFormList>
                <Tooltip title="Add Binding">
                  <Button icon={<PlusOutlined />} onClick={() => add({ binding_name: "", rule_source_id: "", default_target: "", no_resolve: false })} />
                </Tooltip>
              </Space>
            )}
          </Form.List>
        </Form>
      </Modal>
    </Space>
  );
}
