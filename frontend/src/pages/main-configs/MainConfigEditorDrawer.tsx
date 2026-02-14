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
  RuleSource,
  SubscriptionSource,
} from "@/types/api";
import api, { errorDetail } from "@/utils/api";
import useIsMobile from "@/hooks/useIsMobile";

type FinalTargetType = "DIRECT" | "REJECT" | "group";
type ManualMemberType = "filtered_group" | "manual_group";

interface MainConfigEditorDrawerProps {
  open: boolean;
  config: MainConfig | null;
  subscriptions: SubscriptionSource[];
  rules: RuleSource[];
  onClose: () => void;
  onSaved: () => Promise<void>;
}

type EditorFormValues = {
  name: string;
  password_plain: string;
  base_config_yaml: string;
  enabled: boolean;
  final_target_type: FinalTargetType;
  final_target_group_name?: string;
} & Pick<MainConfig, "filtered_groups" | "manual_groups" | "dialer_override_rules" | "route_bindings">;

const DEFAULT_BASE_YAML = "mixed-port: 7890\nmode: rule\n";

const defaultValues: EditorFormValues = {
  name: "",
  password_plain: "",
  base_config_yaml: DEFAULT_BASE_YAML,
  enabled: true,
  final_target_type: "DIRECT",
  final_target_group_name: "",
  filtered_groups: [],
  manual_groups: [],
  dialer_override_rules: [],
  route_bindings: [],
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

function normalizeGroupFields(values: EditorFormValues, rules: RuleSource[]): Pick<MainConfig, "filtered_groups" | "manual_groups" | "dialer_override_rules" | "route_bindings"> {
  return {
    filtered_groups: (values.filtered_groups ?? []).map((group, groupIndex) => ({
      name: group.name,
      position: groupIndex + 1,
      group_mode: group.group_mode,
      test_url: group.test_url ?? null,
      test_interval_sec: group.test_interval_sec ?? null,
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
      test_url: group.test_url ?? null,
      test_interval_sec: group.test_interval_sec ?? null,
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
    route_bindings: (values.route_bindings ?? []).map((item, index) => ({
      position: index + 1,
      binding_name: item.binding_name?.trim() || (rules.find(r => r.id === item.rule_source_id)?.name ?? ""),
      rule_source_id: item.rule_source_id,
      default_group_name: item.default_group_name,
      no_resolve: Boolean(item.no_resolve),
    })),
  };
}

export default function MainConfigEditorDrawer({
  open,
  config,
  subscriptions,
  rules,
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

  const routeDefaultGroupOptions = useMemo(
    () => [
      { label: "DIRECT", value: "DIRECT" },
      { label: "REJECT", value: "REJECT" },
      ...nonRouteGroupOptions,
    ],
    [nonRouteGroupOptions],
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
            matched_proxy_names: [],
            issues: [detail],
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
        name: config.name,
        password_plain: config.password_plain,
        base_config_yaml: config.base_config_yaml,
        enabled: config.enabled,
        final_target_type: config.final_target_type,
        final_target_group_name: config.final_target_group_name ?? "",
        filtered_groups: config.filtered_groups,
        manual_groups: config.manual_groups,
        dialer_override_rules: config.dialer_override_rules,
        route_bindings: config.route_bindings,
      };
      form.setFieldsValue(nextValues);
      queueFilteredGroupPreview(nextValues);
    };

    void init();
  }, [config, form, open, queueFilteredGroupPreview]);

  const handlePreview = async () => {
    try {
      const values = form.getFieldsValue(true) as EditorFormValues;
      setPreviewing(true);
      const groupFields = normalizeGroupFields(values, rules);
      const payload = {
        base_config_yaml: values.base_config_yaml,
        password_plain: values.password_plain,
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

      const groupFields = normalizeGroupFields(values, rules);
      const payload = {
        name: values.name,
        password_plain: values.password_plain,
        base_config_yaml: values.base_config_yaml,
        enabled: values.enabled,
        final_target_type: values.final_target_type,
        final_target_group_name:
          values.final_target_type === "group"
            ? values.final_target_group_name ?? null
            : null,
        ...groupFields,
      };

      if (config) {
        await api.put<MainConfig>(`/admin/main-configs/${config.id}`, payload);
      } else {
        await api.post<MainConfig>("/admin/main-configs", payload);
      }

      void message.success(config ? "Main config updated" : "Main config created");
      await onSaved();
      onClose();
    } catch (error) {
      void message.error(errorDetail(error));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Drawer
      title={config ? `Edit ${config.name}` : "Create Main Config"}
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
          <Col xs={24} sm={12} md={8}>
            <Form.Item
              name="password_plain"
              label="Config Password"
              rules={[{ required: true }]}
            >
              <Input.Password />
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
                              <Form.Item name={[field.name, "test_interval_sec"]} label="Test Interval">
                                <InputNumber min={1} style={{ width: "100%" }} />
                              </Form.Item>
                            </Col>
                            <Col xs={12} sm={5}>
                              <Form.Item name={[field.name, "copy_nodes"]} label="Copy Nodes" valuePropName="checked">
                                <Switch />
                              </Form.Item>
                            </Col>
                          </Row>
                          <Form.Item name={[field.name, "test_url"]} label="Test URL">
                            <Input placeholder="https://www.gstatic.com/generate_204" />
                          </Form.Item>

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

                          <Divider style={{ margin: "12px 0" }} />
                          <Space direction="vertical" style={{ display: "flex" }}>
                            <Typography.Text strong>
                              Matched Proxies Preview
                            </Typography.Text>
                            {filteredGroupPreviews[field.name]?.issues.length ? (
                              <Alert
                                type="warning"
                                showIcon
                                message={filteredGroupPreviews[field.name]?.issues.join(" | ")}
                              />
                            ) : null}
                            <Space wrap>
                              {(filteredGroupPreviews[field.name]?.matched_proxy_names ?? []).map((name) => (
                                <Tag key={name}>{name}</Tag>
                              ))}
                            </Space>
                            {(filteredGroupPreviews[field.name]?.matched_proxy_names ?? []).length === 0 ? (
                              <Typography.Text type="secondary">
                                No matched proxies in current cache.
                              </Typography.Text>
                            ) : null}
                          </Space>
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
                      test_url: "",
                      test_interval_sec: 300,
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
                            <Col xs={12} sm={7}>
                              <Form.Item name={[field.name, "test_interval_sec"]} label="Test Interval">
                                <InputNumber min={1} style={{ width: "100%" }} />
                              </Form.Item>
                            </Col>
                          </Row>
                          <Form.Item name={[field.name, "test_url"]} label="Test URL">
                            <Input placeholder="https://www.gstatic.com/generate_204" />
                          </Form.Item>

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
                      test_url: "",
                      test_interval_sec: 300,
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
        <Typography.Title level={5}>Route Bindings</Typography.Title>
        <Form.List name="route_bindings">
          {(fields, { add, remove, move }) => (
            <Space direction="vertical" style={{ display: "flex" }}>
              {fields.map((field, index) => (
                <Card key={field.key} size="small">
                  <Row gutter={12}>
                    <Col xs={24} sm={12} md={6}>
                      <Form.Item
                        name={[field.name, "rule_source_id"]}
                        label="Rule Source"
                        rules={[{ required: true }]}
                      >
                        <Select
                          options={rules.map((item) => ({
                            label: `${item.name} (${item.behavior})`,
                            value: item.id,
                          }))}
                          showSearch
                        />
                      </Form.Item>
                    </Col>
                    <Col xs={24} sm={12} md={6}>
                      <Form.Item noStyle shouldUpdate>
                        {() => {
                          const ruleSourceId = form.getFieldValue([
                            "route_bindings",
                            field.name,
                            "rule_source_id",
                          ]) as string | undefined;
                          const ruleName = rules.find(r => r.id === ruleSourceId)?.name;
                          return (
                            <Form.Item
                              name={[field.name, "binding_name"]}
                              label="Binding Name"
                            >
                              <Input placeholder={ruleName || "Same as rule source"} />
                            </Form.Item>
                          );
                        }}
                      </Form.Item>
                    </Col>
                    <Col xs={24} sm={12} md={5}>
                      <Form.Item
                        name={[field.name, "default_group_name"]}
                        label="Default Group"
                        rules={[{ required: true }]}
                      >
                        <Select options={routeDefaultGroupOptions} showSearch />
                      </Form.Item>
                    </Col>
                    <Col xs={12} sm={6} md={3}>
                      <Form.Item name={[field.name, "no_resolve"]} label="No Resolve" valuePropName="checked">
                        <Switch />
                      </Form.Item>
                    </Col>
                    <Col xs={12} sm={6} md={4}>
                      <Form.Item label=" ">
                        <Space size={4}>
                          <MoveControls index={index} total={fields.length} onMove={move} />
                          <Tooltip title="Remove">
                            <Button danger icon={<DeleteOutlined />} onClick={() => remove(field.name)} />
                          </Tooltip>
                        </Space>
                      </Form.Item>
                    </Col>
                  </Row>
                </Card>
              ))}
              <Tooltip title="Add Route Binding">
                <Button
                  icon={<PlusOutlined />}
                  onClick={() =>
                    add({
                      binding_name: "",
                      rule_source_id: "",
                      default_group_name: "",
                      no_resolve: false,
                    })
                  }
                />
              </Tooltip>
            </Space>
          )}
        </Form.List>
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
