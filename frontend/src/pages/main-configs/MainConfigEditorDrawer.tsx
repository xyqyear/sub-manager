import {
  Alert,
  Button,
  Card,
  Col,
  Collapse,
  Divider,
  Drawer,
  Form,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Row,
  Select,
  Space,
  Switch,
  Tag,
  Tooltip,
  Typography,
  message,
} from "antd";
import { CloseOutlined, DeleteOutlined, DownOutlined, EyeOutlined, PlusOutlined, SaveOutlined, UpOutlined } from "@ant-design/icons";
import { type MouseEvent, useCallback, useEffect, useMemo, useState } from "react";
import type {
  FilteredGroupPreviewResponse,
  GroupMode,
  MainConfig,
  PreviewResponse,
  RouteTemplate,
  RuleSourceListItem,
  SubscriptionSourceListItem,
} from "@/types/api";
import api, { errorDetail } from "@/utils/api";
import useIsMobile from "@/hooks/useIsMobile";

type FinalTargetType = "DIRECT" | "REJECT" | "group";
type ManualMemberType = "filtered_group" | "manual_group";

type EditorMode = "create" | "edit" | "duplicate";

interface MainConfigEditorDrawerProps {
  open: boolean;
  config: MainConfig | null;
  mode: EditorMode;
  subscriptions: SubscriptionSourceListItem[];
  rules: RuleSourceListItem[];
  routeTemplates: RouteTemplate[];
  onClose: () => void;
  onSaved: () => Promise<void>;
}

type SlotMappingFormValue = { slot_name: string; group_name: string };

type EditorFormValues = {
  name: string;
  base_config_yaml: string;
  enabled: boolean;
  final_target_type: FinalTargetType;
  final_target_group_name?: string;
  test_url?: string;
  test_interval_sec?: number;
  route_template_id?: string;
  slot_mappings: SlotMappingFormValue[];
} & Pick<MainConfig, "filtered_groups" | "manual_groups" | "dialer_override_rules">;

const DEFAULT_BASE_YAML = "mixed-port: 7890\nmode: rule\n";

const defaultValues: EditorFormValues = {
  name: "",
  base_config_yaml: DEFAULT_BASE_YAML,
  enabled: true,
  final_target_type: "DIRECT",
  final_target_group_name: "",
  test_url: "",
  test_interval_sec: undefined,
  filtered_groups: [],
  manual_groups: [],
  dialer_override_rules: [],
  route_template_id: undefined,
  slot_mappings: [],
};

const groupModeOptions: { label: string; value: GroupMode }[] = [
  { label: "select", value: "select" },
  { label: "fallback", value: "fallback" },
  { label: "url-test", value: "url-test" },
];

type MoveControlsProps = {
  index: number;
  total: number;
  onMove: (from: number, to: number) => void;
};

function MoveControls({ index, total, onMove }: MoveControlsProps) {
  const handleMove =
    (offset: -1 | 1) =>
    (event: MouseEvent<HTMLElement>) => {
      event.stopPropagation();
      const nextIndex = index + offset;
      if (nextIndex < 0 || nextIndex >= total) {
        return;
      }
      onMove(index, nextIndex);
    };

  return (
    <Space.Compact>
      <Tooltip title="Move Up">
        <Button
          type="text"
          size="small"
          icon={<UpOutlined />}
          disabled={index === 0}
          onClick={handleMove(-1)}
        />
      </Tooltip>
      <Tooltip title="Move Down">
        <Button
          type="text"
          size="small"
          icon={<DownOutlined />}
          disabled={index >= total - 1}
          onClick={handleMove(1)}
        />
      </Tooltip>
    </Space.Compact>
  );
}

function normalizeGroupFields(values: EditorFormValues): Pick<MainConfig, "filtered_groups" | "manual_groups" | "dialer_override_rules"> & { test_url: string | null; test_interval_sec: number | null; route_template_id: string | null; slot_mappings: { slot_name: string; group_name: string }[] } {
  return {
    filtered_groups: (values.filtered_groups ?? []).map((group, groupIndex) => ({
      name: group.name,
      position: groupIndex + 1,
      group_mode: group.group_mode,
      copy_nodes: Boolean(group.copy_nodes),
      rules: (group.rules ?? []).map((rule, ruleIndex) => ({
        subscription_source_id: rule.subscription_source_id,
        regex_pattern: rule.regex_pattern,
        regex_flags: rule.regex_flags,
        position: ruleIndex + 1,
      })),
    })),
    manual_groups: (values.manual_groups ?? []).map((group, groupIndex) => ({
      name: group.name,
      position: groupIndex + 1,
      group_mode: group.group_mode,
      members: (group.members ?? []).map((member, memberIndex) => ({
        member_type: member.member_type,
        member_ref: member.member_ref,
        position: memberIndex + 1,
      })),
    })),
    dialer_override_rules: (values.dialer_override_rules ?? []).map((item) => ({
      filtered_group_name: item.filtered_group_name,
      dialer_group_name: item.dialer_group_name,
    })),
    test_url: values.test_url || null,
    test_interval_sec: values.test_interval_sec ?? null,
    route_template_id: values.route_template_id || null,
    slot_mappings: (values.slot_mappings ?? []).map((m) => ({
      slot_name: m.slot_name,
      group_name: m.group_name,
    })),
  };
}

export default function MainConfigEditorDrawer({
  open,
  config,
  mode,
  subscriptions,
  rules,
  routeTemplates,
  onClose,
  onSaved,
}: MainConfigEditorDrawerProps) {
  const [form] = Form.useForm<EditorFormValues>();
  const isMobile = useIsMobile();
  const [saving, setSaving] = useState(false);
  const [filteredGroupPreviews, setFilteredGroupPreviews] =
    useState<FilteredGroupPreviewResponse["groups"]>([]);
  const [previewing, setPreviewing] = useState(false);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewYaml, setPreviewYaml] = useState("");
  const [previewDiagnostics, setPreviewDiagnostics] = useState<PreviewResponse["diagnostics"] | null>(null);

  const finalTargetType = Form.useWatch("final_target_type", form);
  const filteredGroupsWatch = Form.useWatch("filtered_groups", form);
  const manualGroupsWatch = Form.useWatch("manual_groups", form);
  const routeTemplateIdWatch = Form.useWatch("route_template_id", form);

  const selectedTemplate = useMemo(
    () => routeTemplates.find((t) => t.id === routeTemplateIdWatch) ?? null,
    [routeTemplates, routeTemplateIdWatch],
  );

  const nonRouteGroupOptions = useMemo(
    () => [
      ...(filteredGroupsWatch ?? [])
        .filter((item) => item?.name)
        .map((item) => ({ label: item.name, value: item.name })),
      ...(manualGroupsWatch ?? [])
        .filter((item) => item?.name)
        .map((item) => ({ label: item.name, value: item.name })),
    ],
    [filteredGroupsWatch, manualGroupsWatch],
  );

  const filteredGroupOptions = useMemo(
    () =>
      (filteredGroupsWatch ?? [])
        .filter((item) => item?.name)
        .map((item) => ({ label: item.name, value: item.name })),
    [filteredGroupsWatch],
  );

  const manualGroupOptions = useMemo(
    () =>
      (manualGroupsWatch ?? [])
        .filter((item) => item?.name)
        .map((item) => ({ label: item.name, value: item.name })),
    [manualGroupsWatch],
  );

  const triggerFilteredGroupPreview = useCallback(
    async (valuesOverride?: Partial<EditorFormValues>) => {
      if (!open) {
        setFilteredGroupPreviews([]);
        return;
      }

      const values =
        valuesOverride ??
        (form.getFieldsValue([
          "filtered_groups",
        ]) as Partial<EditorFormValues>);
      const filteredGroups = values.filtered_groups ?? [];
      if (!filteredGroups.length) {
        setFilteredGroupPreviews([]);
        return;
      }

      const payload = {
        filtered_groups: filteredGroups.map((group) => ({
          name: group.name || null,
          rules: (group.rules ?? []).map((rule, index) => ({
            subscription_source_id: rule.subscription_source_id || null,
            regex_pattern: rule.regex_pattern || null,
            regex_flags: rule.regex_flags ?? "",
            position: index + 1,
          })),
        })),
      };

      try {
        const response = await api.post<FilteredGroupPreviewResponse>(
          "/admin/main-configs/filtered-groups/preview",
          payload,
        );
        setFilteredGroupPreviews(response.data.groups);
      } catch (error: unknown) {
        const detail = errorDetail(error);
        setFilteredGroupPreviews(
          filteredGroups.map((group, index) => ({
            name: group.name || `Filtered Group #${index + 1}`,
            rule_results: (group.rules ?? []).map(() => ({
              matched_proxy_names: [],
              issue: detail,
            })),
          })),
        );
      }
    },
    [form, open],
  );

  const queueFilteredGroupPreview = useCallback(
    (valuesOverride?: Partial<EditorFormValues>) => {
      window.setTimeout(() => {
        void triggerFilteredGroupPreview(valuesOverride);
      }, 0);
    },
    [triggerFilteredGroupPreview],
  );

  useEffect(() => {
    if (!open) {
      return;
    }

    const init = async () => {
      if (!config) {
        form.resetFields();
        form.setFieldsValue(defaultValues);
        queueFilteredGroupPreview(defaultValues);
        return;
      }

      form.resetFields();
      const nextValues: EditorFormValues = {
        ...defaultValues,
        name: mode === "duplicate" ? `${config.name} (Copy)` : config.name,
        base_config_yaml: config.base_config_yaml,
        enabled: config.enabled,
        final_target_type: config.final_target_type,
        final_target_group_name: config.final_target_group_name ?? "",
        test_url: config.test_url ?? "",
        test_interval_sec: config.test_interval_sec ?? undefined,
        filtered_groups: config.filtered_groups,
        manual_groups: config.manual_groups,
        dialer_override_rules: config.dialer_override_rules,
        route_template_id: config.route_template_id ?? undefined,
        slot_mappings: config.slot_mappings ?? [],
      };
      form.setFieldsValue(nextValues);
      queueFilteredGroupPreview(nextValues);
    };

    void init();
  }, [config, mode, form, open, queueFilteredGroupPreview]);

  const handlePreview = async () => {
    try {
      const values = form.getFieldsValue(true) as EditorFormValues;
      setPreviewing(true);
      const groupFields = normalizeGroupFields(values);
      const payload = {
        base_config_yaml: values.base_config_yaml,
        final_target_type: values.final_target_type,
        final_target_group_name:
          values.final_target_type === "group"
            ? values.final_target_group_name ?? null
            : null,
        config_id: config?.id ?? null,
        ...groupFields,
      };
      const response = await api.post<PreviewResponse>(
        "/admin/main-configs/preview-draft",
        payload,
      );
      setPreviewYaml(response.data.yaml);
      setPreviewDiagnostics(response.data.diagnostics);
      setPreviewOpen(true);
    } catch (error) {
      void message.error(errorDetail(error));
    } finally {
      setPreviewing(false);
    }
  };

  const submit = async () => {
    try {
      const values = await form.validateFields();
      setSaving(true);

      const groupFields = normalizeGroupFields(values);
      const payload = {
        name: values.name,
        base_config_yaml: values.base_config_yaml,
        enabled: values.enabled,
        final_target_type: values.final_target_type,
        final_target_group_name:
          values.final_target_type === "group"
            ? values.final_target_group_name ?? null
            : null,
        ...groupFields,
      };

      if (mode === "edit" && config) {
        await api.put<MainConfig>(`/admin/main-configs/${config.id}`, payload);
      } else {
        await api.post<MainConfig>("/admin/main-configs", payload);
      }

      void message.success(mode === "edit" ? "Main config updated" : "Main config created");
      await onSaved();
      onClose();
    } catch (error) {
      if (error && typeof error === "object" && "errorFields" in error) {
        void message.error("Please fill in all required fields");
        return;
      }
      void message.error(errorDetail(error));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Drawer
      title={mode === "edit" ? `Edit ${config?.name}` : mode === "duplicate" ? "Duplicate Main Config" : "Create Main Config"}
      open={open}
      onClose={onClose}
      width={isMobile ? "100%" : 1200}
      destroyOnHidden
      extra={
        <Space>
          <Tooltip title="Preview">
            <Button icon={<EyeOutlined />} onClick={() => void handlePreview()} loading={previewing} />
          </Tooltip>
          <Tooltip title="Cancel">
            <Button icon={<CloseOutlined />} onClick={onClose} />
          </Tooltip>
          <Tooltip title="Save">
            <Button type="primary" icon={<SaveOutlined />} loading={saving} onClick={() => void submit()} />
          </Tooltip>
        </Space>
      }
    >
      <Form form={form} layout="vertical" initialValues={defaultValues}>
        <Typography.Title level={5}>Main Settings</Typography.Title>

        <Row gutter={12}>
          <Col xs={24} sm={12} md={8}>
            <Form.Item name="name" label="Config Name" rules={[{ required: true }]}>
              <Input />
            </Form.Item>
          </Col>
          <Col xs={12} sm={6} md={4}>
            <Form.Item name="enabled" label="Enabled" valuePropName="checked">
              <Switch />
            </Form.Item>
          </Col>
        </Row>

        <Row gutter={12}>
          <Col xs={24} sm={12} md={8}>
            <Form.Item
              name="final_target_type"
              label="Final Target Type"
              rules={[{ required: true }]}
            >
              <Select
                options={[
                  { label: "DIRECT", value: "DIRECT" },
                  { label: "REJECT", value: "REJECT" },
                  { label: "group", value: "group" },
                ]}
              />
            </Form.Item>
          </Col>
          {finalTargetType === "group" ? (
            <Col xs={24} sm={12} md={8}>
              <Form.Item
                name="final_target_group_name"
                label="Final Target Group"
                rules={[{ required: true }]}
              >
                <Select options={nonRouteGroupOptions} showSearch />
              </Form.Item>
            </Col>
          ) : null}
        </Row>

        <Form.Item
          name="base_config_yaml"
          label="Base Config YAML"
          rules={[{ required: true, message: "base_config_yaml is required" }]}
          extra="Base config stays manual by design."
        >
          <Input.TextArea rows={10} />
        </Form.Item>

        <Row gutter={12}>
          <Col xs={24} sm={12} md={8}>
            <Form.Item name="test_url" label="Test URL">
              <Input placeholder="https://www.gstatic.com/generate_204" />
            </Form.Item>
          </Col>
          <Col xs={12} sm={6} md={4}>
            <Form.Item name="test_interval_sec" label="Test Interval (sec)">
              <InputNumber min={1} style={{ width: "100%" }} />
            </Form.Item>
          </Col>
        </Row>

        <Divider />
        <Typography.Title level={5}>Filtered Groups</Typography.Title>
        <Form.List name="filtered_groups">
          {(fields, { add, remove, move }) => (
            <Space direction="vertical" style={{ display: "flex" }}>
              {fields.map((field, groupIndex) => (
                <Collapse
                  key={field.key}
                  defaultActiveKey={["content"]}
                  items={[
                    {
                      key: "content",
                      label:
                        filteredGroupsWatch?.[field.name]?.name?.trim() ||
                        `Filtered Group #${groupIndex + 1}`,
                      extra: (
                        <Space size={4}>
                          <MoveControls
                            index={groupIndex}
                            total={fields.length}
                            onMove={(from, to) => {
                              move(from, to);
                              queueFilteredGroupPreview();
                            }}
                          />
                          <Popconfirm
                            title="Remove this filtered group?"
                            onConfirm={() => {
                              remove(field.name);
                              queueFilteredGroupPreview();
                            }}
                          >
                            <Tooltip title="Remove">
                              <Button
                                danger
                                size="small"
                                icon={<DeleteOutlined />}
                                onClick={(event) => event.stopPropagation()}
                              />
                            </Tooltip>
                          </Popconfirm>
                        </Space>
                      ),
                      children: (
                        <Space direction="vertical" style={{ display: "flex" }}>
                          <Row gutter={12}>
                            <Col xs={24} sm={8}>
                              <Form.Item
                                name={[field.name, "name"]}
                                label="Group Name"
                                rules={[{ required: true }]}
                              >
                                <Input onBlur={() => void triggerFilteredGroupPreview()} />
                              </Form.Item>
                            </Col>
                            <Col xs={12} sm={6}>
                              <Form.Item
                                name={[field.name, "group_mode"]}
                                label="Mode"
                                rules={[{ required: true }]}
                              >
                                <Select options={groupModeOptions} />
                              </Form.Item>
                            </Col>
                            <Col xs={12} sm={5}>
                              <Form.Item name={[field.name, "copy_nodes"]} label="Copy Nodes" valuePropName="checked">
                                <Switch />
                              </Form.Item>
                            </Col>
                          </Row>

                          <Form.List name={[field.name, "rules"]}>
                            {(ruleFields, ruleOps) => (
                              <Space direction="vertical" style={{ display: "flex" }}>
                                <Typography.Text strong>Rules</Typography.Text>
                                {ruleFields.map((ruleField, ruleIndex) => (
                                  <Card key={ruleField.key} size="small">
                                    <Row gutter={12}>
                                      <Col xs={24} sm={8}>
                                        <Form.Item
                                          name={[ruleField.name, "subscription_source_id"]}
                                          label="Subscription"
                                          rules={[{ required: true }]}
                                        >
                                          <Select
                                            options={subscriptions.map((item) => ({
                                              label: item.name,
                                              value: item.id,
                                            }))}
                                            onBlur={() => void triggerFilteredGroupPreview()}
                                          />
                                        </Form.Item>
                                      </Col>
                                      <Col xs={16} sm={8}>
                                        <Form.Item
                                          name={[ruleField.name, "regex_pattern"]}
                                          label="Regex"
                                          rules={[{ required: true }]}
                                        >
                                          <Input onBlur={() => void triggerFilteredGroupPreview()} />
                                        </Form.Item>
                                      </Col>
                                      <Col xs={8} sm={4}>
                                        <Form.Item name={[ruleField.name, "regex_flags"]} label="Flags">
                                          <Input
                                            placeholder="i"
                                            onBlur={() => void triggerFilteredGroupPreview()}
                                          />
                                        </Form.Item>
                                      </Col>
                                      <Col xs={24} sm={4}>
                                        <Form.Item label=" ">
                                          <Space size={4}>
                                            <MoveControls
                                              index={ruleIndex}
                                              total={ruleFields.length}
                                              onMove={(from, to) => {
                                                ruleOps.move(from, to);
                                                queueFilteredGroupPreview();
                                              }}
                                            />
                                            <Tooltip title="Delete">
                                              <Button
                                                danger
                                                icon={<DeleteOutlined />}
                                                onClick={() => {
                                                  ruleOps.remove(ruleField.name);
                                                  queueFilteredGroupPreview();
                                                }}
                                              />
                                            </Tooltip>
                                          </Space>
                                        </Form.Item>
                                      </Col>
                                    </Row>
                                    {(() => {
                                      const ruleResult = filteredGroupPreviews[field.name]?.rule_results?.[ruleField.name];
                                      if (!ruleResult) return null;
                                      return (
                                        <div style={{ marginTop: 8 }}>
                                          {ruleResult.issue ? (
                                            <Alert type="warning" showIcon message={ruleResult.issue} style={{ marginBottom: 4 }} />
                                          ) : ruleResult.matched_proxy_names.length > 0 ? (
                                            <Space wrap>
                                              {ruleResult.matched_proxy_names.map((name) => (
                                                <Tag key={name}>{name}</Tag>
                                              ))}
                                            </Space>
                                          ) : (
                                            <Typography.Text type="secondary">No matched proxies</Typography.Text>
                                          )}
                                        </div>
                                      );
                                    })()}
                                  </Card>
                                ))}
                                <Tooltip title="Add Filter Rule">
                                  <Button
                                    icon={<PlusOutlined />}
                                    onClick={() => {
                                      ruleOps.add({
                                        subscription_source_id: "",
                                        regex_pattern: ".*",
                                        regex_flags: "",
                                      });
                                      queueFilteredGroupPreview();
                                    }}
                                  />
                                </Tooltip>
                              </Space>
                            )}
                          </Form.List>
                        </Space>
                      ),
                    },
                  ]}
                />
              ))}
              <Tooltip title="Add Filtered Group">
                <Button
                  icon={<PlusOutlined />}
                  onClick={() => {
                    add({
                      name: "",
                      group_mode: "select",
                      copy_nodes: false,
                      rules: [],
                    });
                    queueFilteredGroupPreview();
                  }}
                />
              </Tooltip>
            </Space>
          )}
        </Form.List>

        <Divider />
        <Typography.Title level={5}>Manual Groups</Typography.Title>
        <Form.List name="manual_groups">
          {(fields, { add, remove, move }) => (
            <Space direction="vertical" style={{ display: "flex" }}>
              {fields.map((field, groupIndex) => (
                <Collapse
                  key={field.key}
                  defaultActiveKey={["content"]}
                  items={[
                    {
                      key: "content",
                      label:
                        manualGroupsWatch?.[field.name]?.name?.trim() ||
                        `Manual Group #${groupIndex + 1}`,
                      extra: (
                        <Space size={4}>
                          <MoveControls
                            index={groupIndex}
                            total={fields.length}
                            onMove={move}
                          />
                          <Popconfirm
                            title="Remove this manual group?"
                            onConfirm={() => remove(field.name)}
                          >
                            <Tooltip title="Remove">
                              <Button
                                danger
                                size="small"
                                icon={<DeleteOutlined />}
                                onClick={(event) => event.stopPropagation()}
                              />
                            </Tooltip>
                          </Popconfirm>
                        </Space>
                      ),
                      children: (
                        <Space direction="vertical" style={{ display: "flex" }}>
                          <Row gutter={12}>
                            <Col xs={24} sm={10}>
                              <Form.Item
                                name={[field.name, "name"]}
                                label="Group Name"
                                rules={[{ required: true }]}
                              >
                                <Input />
                              </Form.Item>
                            </Col>
                            <Col xs={12} sm={7}>
                              <Form.Item
                                name={[field.name, "group_mode"]}
                                label="Mode"
                                rules={[{ required: true }]}
                              >
                                <Select options={groupModeOptions} />
                              </Form.Item>
                            </Col>
                          </Row>

                          <Form.List name={[field.name, "members"]}>
                            {(memberFields, memberOps) => (
                              <Space direction="vertical" style={{ display: "flex" }}>
                                <Typography.Text strong>Members</Typography.Text>
                                {memberFields.map((memberField, memberIndex) => (
                                  <Card key={memberField.key} size="small">
                                    <Row gutter={12}>
                                      <Col xs={24} sm={6}>
                                        <Form.Item
                                          name={[memberField.name, "member_type"]}
                                          label="Type"
                                          rules={[{ required: true }]}
                                        >
                                          <Select
                                            options={[
                                              { label: "filtered_group", value: "filtered_group" },
                                              { label: "manual_group", value: "manual_group" },
                                            ]}
                                          />
                                        </Form.Item>
                                      </Col>
                                      <Col xs={24} sm={12}>
                                        <Form.Item noStyle shouldUpdate>
                                          {() => {
                                            const memberType = form.getFieldValue([
                                              "manual_groups",
                                              field.name,
                                              "members",
                                              memberField.name,
                                              "member_type",
                                            ]) as ManualMemberType | undefined;

                                            if (memberType === "filtered_group") {
                                              return (
                                                <Form.Item
                                                  name={[memberField.name, "member_ref"]}
                                                  label="Member"
                                                  rules={[{ required: true }]}
                                                >
                                                  <Select options={filteredGroupOptions} showSearch />
                                                </Form.Item>
                                              );
                                            }

                                            if (memberType === "manual_group") {
                                              return (
                                                <Form.Item
                                                  name={[memberField.name, "member_ref"]}
                                                  label="Member"
                                                  rules={[{ required: true }]}
                                                >
                                                  <Select options={manualGroupOptions} showSearch />
                                                </Form.Item>
                                              );
                                            }

                                            return null;
                                          }}
                                        </Form.Item>
                                      </Col>
                                      <Col xs={24} sm={6}>
                                        <Form.Item label=" ">
                                          <Space size={4}>
                                            <MoveControls
                                              index={memberIndex}
                                              total={memberFields.length}
                                              onMove={memberOps.move}
                                            />
                                            <Tooltip title="Delete">
                                              <Button danger icon={<DeleteOutlined />} onClick={() => memberOps.remove(memberField.name)} />
                                            </Tooltip>
                                          </Space>
                                        </Form.Item>
                                      </Col>
                                    </Row>
                                  </Card>
                                ))}
                                <Tooltip title="Add Manual Member">
                                  <Button
                                    icon={<PlusOutlined />}
                                    onClick={() =>
                                      memberOps.add({
                                        member_type: "filtered_group",
                                        member_ref: "",
                                      })
                                    }
                                  />
                                </Tooltip>
                              </Space>
                            )}
                          </Form.List>
                        </Space>
                      ),
                    },
                  ]}
                />
              ))}
              <Tooltip title="Add Manual Group">
                <Button
                  icon={<PlusOutlined />}
                  onClick={() =>
                    add({
                      name: "",
                      group_mode: "select",
                      members: [],
                    })
                  }
                />
              </Tooltip>
            </Space>
          )}
        </Form.List>

        <Divider />
        <Typography.Title level={5}>Dialer Overrides</Typography.Title>
        <Form.List name="dialer_override_rules">
          {(fields, { add, remove, move }) => (
            <Space direction="vertical" style={{ display: "flex" }}>
              {fields.map((field, index) => (
                <Card key={field.key} size="small">
                  <Row gutter={12}>
                    <Col xs={24} sm={10}>
                      <Form.Item
                        name={[field.name, "filtered_group_name"]}
                        label="Filtered Group"
                        rules={[{ required: true }]}
                      >
                        <Select options={filteredGroupOptions} showSearch />
                      </Form.Item>
                    </Col>
                    <Col xs={24} sm={8}>
                      <Form.Item
                        name={[field.name, "dialer_group_name"]}
                        label="Dialer Group"
                        rules={[{ required: true }]}
                      >
                        <Select options={nonRouteGroupOptions} showSearch />
                      </Form.Item>
                    </Col>
                    <Col xs={24} sm={4}>
                      <Form.Item label=" ">
                        <Space size={4}>
                          <MoveControls index={index} total={fields.length} onMove={move} />
                          <Tooltip title="Delete">
                            <Button danger icon={<DeleteOutlined />} onClick={() => remove(field.name)} />
                          </Tooltip>
                        </Space>
                      </Form.Item>
                    </Col>
                  </Row>
                </Card>
              ))}
              <Tooltip title="Add Dialer Override">
                <Button
                  icon={<PlusOutlined />}
                  onClick={() =>
                    add({
                      filtered_group_name: "",
                      dialer_group_name: "",
                    })
                  }
                />
              </Tooltip>
            </Space>
          )}
        </Form.List>

        <Divider />
        <Typography.Title level={5}>Route Template</Typography.Title>
        <Row gutter={12}>
          <Col xs={24} sm={12}>
            <Form.Item name="route_template_id" label="Route Template">
              <Select
                allowClear
                placeholder="No route template"
                options={routeTemplates.map((t) => ({ label: t.name, value: t.id }))}
                showSearch
                onChange={() => {
                  form.setFieldValue("slot_mappings", []);
                }}
              />
            </Form.Item>
          </Col>
        </Row>

        {selectedTemplate && selectedTemplate.slots.length > 0 && (
          <Card size="small" title="Slot Mappings">
            <Form.List name="slot_mappings">
              {(fields) => {
                const currentMappings = form.getFieldValue("slot_mappings") as SlotMappingFormValue[] | undefined;
                const needsSync = selectedTemplate.slots.length !== (currentMappings?.length ?? 0) ||
                  selectedTemplate.slots.some((slot, i) => currentMappings?.[i]?.slot_name !== slot.name);

                if (needsSync) {
                  const existingMap = new Map((currentMappings ?? []).map((m) => [m.slot_name, m.group_name]));
                  const synced = selectedTemplate.slots.map((slot) => ({
                    slot_name: slot.name,
                    group_name: existingMap.get(slot.name) ?? "",
                  }));
                  window.setTimeout(() => form.setFieldValue("slot_mappings", synced), 0);
                }

                return (
                  <Space direction="vertical" style={{ display: "flex" }}>
                    {fields.map((field, index) => {
                      const slotName = selectedTemplate.slots[index]?.name ?? `Slot ${index + 1}`;
                      return (
                        <Row key={field.key} gutter={12} align="middle">
                          <Col xs={8}>
                            <Typography.Text strong>{slotName}</Typography.Text>
                            <Form.Item name={[field.name, "slot_name"]} hidden>
                              <Input />
                            </Form.Item>
                          </Col>
                          <Col xs={16}>
                            <Form.Item
                              name={[field.name, "group_name"]}
                              rules={[{ required: true, message: "Select a group" }]}
                              style={{ marginBottom: 0 }}
                            >
                              <Select options={nonRouteGroupOptions} showSearch placeholder="Select group" />
                            </Form.Item>
                          </Col>
                        </Row>
                      );
                    })}
                  </Space>
                );
              }}
            </Form.List>
          </Card>
        )}
      </Form>

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
    </Drawer>
  );
}
