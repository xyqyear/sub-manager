import { useState, useEffect, useCallback, useMemo } from "react";
import { toast } from "sonner";
import { Plus, Trash2, Import, Eye, AlertTriangle } from "lucide-react";
import { useForm, useFieldArray, Controller } from "react-hook-form";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Separator } from "@/components/ui/separator";
import { ConfirmPopover } from "@/components/ui/confirm-popover";
import SortableFormList from "@/components/dnd/SortableFormList";
import { InsertAboveOutlined, InsertBelowOutlined } from "@/components/icons";
import api, { errorDetail } from "@/utils/api";
import type {
  MainConfig,
  SubscriptionSourceListItem,
  RouteTemplate,
  PreviewResponse,
  FilteredGroupPreviewResponse,
} from "@/types/api";

type FinalTargetType = "DIRECT" | "REJECT" | "group";
type EditorMode = "create" | "edit" | "duplicate";

type EditorFormValues = {
  name: string;
  base_config_yaml: string;
  enabled: boolean;
  final_target_type: FinalTargetType;
  final_target_group_name: string;
  test_url: string;
  test_interval_sec: number | undefined;
  route_template_id: string;
  slot_mappings: { slot_name: string; group_name: string }[];
  filtered_groups: {
    name: string;
    group_mode: string;
    copy_nodes: boolean;
    rules: {
      subscription_source_id: string;
      regex_pattern: string;
      regex_flags: string;
    }[];
  }[];
  manual_groups: {
    name: string;
    group_mode: string;
    members: {
      member_type: string;
      member_ref: string;
    }[];
  }[];
  dialer_override_rules: {
    filtered_group_name: string;
    dialer_group_name: string;
  }[];
};

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
  route_template_id: "",
  slot_mappings: [],
};

const groupModeOptions = [
  { label: "select", value: "select" },
  { label: "fallback", value: "fallback" },
  { label: "url-test", value: "url-test" },
];

function normalizeGroupFields(values: EditorFormValues) {
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

interface MainConfigEditorDrawerProps {
  open: boolean;
  config: MainConfig | null;
  mode: EditorMode;
  configs: MainConfig[];
  subscriptions: SubscriptionSourceListItem[];
  routeTemplates: RouteTemplate[];
  onClose: () => void;
  onSaved: () => Promise<void>;
}

export default function MainConfigEditorDrawer({
  open,
  config,
  mode,
  configs,
  subscriptions,
  routeTemplates,
  onClose,
  onSaved,
}: MainConfigEditorDrawerProps) {
  const [saving, setSaving] = useState(false);
  const [filteredGroupPreviews, setFilteredGroupPreviews] = useState<FilteredGroupPreviewResponse["groups"]>([]);
  const [previewing, setPreviewing] = useState(false);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [importSourceId, setImportSourceId] = useState<string>("");
  const [previewYaml, setPreviewYaml] = useState("");
  const [previewDiagnostics, setPreviewDiagnostics] = useState<PreviewResponse["diagnostics"] | null>(null);

  const form = useForm<EditorFormValues>({ defaultValues });
  const finalTargetType = form.watch("final_target_type");
  const filteredGroupsWatch = form.watch("filtered_groups");
  const manualGroupsWatch = form.watch("manual_groups");
  const routeTemplateIdWatch = form.watch("route_template_id");

  const filteredGroupsField = useFieldArray({ control: form.control, name: "filtered_groups" });
  const manualGroupsField = useFieldArray({ control: form.control, name: "manual_groups" });
  const dialerOverridesField = useFieldArray({ control: form.control, name: "dialer_override_rules" });
  const slotMappingsField = useFieldArray({ control: form.control, name: "slot_mappings" });

  const selectedTemplate = useMemo(
    () => routeTemplates.find((t) => t.id === routeTemplateIdWatch) ?? null,
    [routeTemplates, routeTemplateIdWatch]
  );

  const nonRouteGroupOptions = useMemo(() => [
    ...(filteredGroupsWatch ?? []).filter((g) => g?.name).map((g) => ({ label: g.name, value: g.name })),
    ...(manualGroupsWatch ?? []).filter((g) => g?.name).map((g) => ({ label: g.name, value: g.name })),
  ], [filteredGroupsWatch, manualGroupsWatch]);

  const filteredGroupOptions = useMemo(
    () => (filteredGroupsWatch ?? []).filter((g) => g?.name).map((g) => ({ label: g.name, value: g.name })),
    [filteredGroupsWatch]
  );

  const manualGroupOptions = useMemo(
    () => (manualGroupsWatch ?? []).filter((g) => g?.name).map((g) => ({ label: g.name, value: g.name })),
    [manualGroupsWatch]
  );

  const importConfigOptions = useMemo(
    () => configs.filter((c) => c.id !== config?.id).map((c) => ({ label: c.name, value: c.id })),
    [configs, config]
  );

  // Filtered group preview
  const triggerFilteredGroupPreview = useCallback(
    async (valuesOverride?: Partial<EditorFormValues>) => {
      if (!open) {
        setFilteredGroupPreviews([]);
        return;
      }
      const values = valuesOverride ?? form.getValues();
      const fg = values.filtered_groups ?? [];
      if (!fg.length) {
        setFilteredGroupPreviews([]);
        return;
      }
      const payload = {
        filtered_groups: fg.map((group) => ({
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
        const res = await api.post<FilteredGroupPreviewResponse>(
          "/admin/main-configs/filtered-groups/preview",
          payload,
        );
        setFilteredGroupPreviews(res.data.groups);
      } catch (error) {
        const detail = errorDetail(error);
        setFilteredGroupPreviews(
          fg.map((group, index) => ({
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

  // Import from another config
  const handleImportConfirm = useCallback(() => {
    const source = configs.find((c) => c.id === importSourceId);
    if (!source) return;
    const nextValues: Partial<EditorFormValues> = {
      base_config_yaml: source.base_config_yaml,
      final_target_type: source.final_target_type,
      final_target_group_name: source.final_target_group_name ?? "",
      test_url: source.test_url ?? "",
      test_interval_sec: source.test_interval_sec ?? undefined,
      filtered_groups: source.filtered_groups.map((g) => ({
        name: g.name,
        group_mode: g.group_mode,
        copy_nodes: g.copy_nodes ?? false,
        rules: g.rules.map((r) => ({
          subscription_source_id: r.subscription_source_id,
          regex_pattern: r.regex_pattern,
          regex_flags: r.regex_flags,
        })),
      })),
      manual_groups: source.manual_groups.map((g) => ({
        name: g.name,
        group_mode: g.group_mode,
        members: g.members.map((m) => ({
          member_type: m.member_type,
          member_ref: m.member_ref,
        })),
      })),
      dialer_override_rules: source.dialer_override_rules,
      route_template_id: source.route_template_id ?? "",
      slot_mappings: source.slot_mappings ?? [],
    };
    // Reset with current name/enabled preserved
    const currentName = form.getValues("name");
    const currentEnabled = form.getValues("enabled");
    form.reset({ ...defaultValues, ...nextValues, name: currentName, enabled: currentEnabled });
    setImportOpen(false);
    setImportSourceId("");
    queueFilteredGroupPreview(nextValues);
  }, [configs, importSourceId, form, queueFilteredGroupPreview]);

  // Initialization
  useEffect(() => {
    if (!open) return;
    if (!config) {
      form.reset(defaultValues);
      queueFilteredGroupPreview(defaultValues);
      return;
    }
    const nextValues: EditorFormValues = {
      ...defaultValues,
      name: mode === "duplicate" ? `${config.name} (Copy)` : config.name,
      base_config_yaml: config.base_config_yaml,
      enabled: config.enabled,
      final_target_type: config.final_target_type,
      final_target_group_name: config.final_target_group_name ?? "",
      test_url: config.test_url ?? "",
      test_interval_sec: config.test_interval_sec ?? undefined,
      filtered_groups: config.filtered_groups.map((g) => ({
        name: g.name,
        group_mode: g.group_mode,
        copy_nodes: g.copy_nodes ?? false,
        rules: g.rules.map((r) => ({
          subscription_source_id: r.subscription_source_id,
          regex_pattern: r.regex_pattern,
          regex_flags: r.regex_flags,
        })),
      })),
      manual_groups: config.manual_groups.map((g) => ({
        name: g.name,
        group_mode: g.group_mode,
        members: g.members.map((m) => ({
          member_type: m.member_type,
          member_ref: m.member_ref,
        })),
      })),
      dialer_override_rules: config.dialer_override_rules,
      route_template_id: config.route_template_id ?? "",
      slot_mappings: config.slot_mappings ?? [],
    };
    form.reset(nextValues);
    queueFilteredGroupPreview(nextValues);
  }, [config, mode, form, open, queueFilteredGroupPreview]);

  // Slot mapping auto-sync
  useEffect(() => {
    if (!selectedTemplate) return;
    const currentMappings = form.getValues("slot_mappings");
    const needsSync =
      selectedTemplate.slots.length !== currentMappings?.length ||
      selectedTemplate.slots.some((slot, i) => currentMappings?.[i]?.slot_name !== slot.name);
    if (needsSync) {
      const existingMap = new Map((currentMappings ?? []).map((m) => [m.slot_name, m.group_name]));
      const synced = selectedTemplate.slots.map((slot) => ({
        slot_name: slot.name,
        group_name: existingMap.get(slot.name) ?? "",
      }));
      window.setTimeout(() => {
        slotMappingsField.replace(synced);
      }, 0);
    }
  }, [selectedTemplate, form, slotMappingsField]);

  // Draft preview
  const handlePreview = async () => {
    const values = form.getValues();
    setPreviewing(true);
    try {
      const groupFields = normalizeGroupFields(values);
      const payload = {
        base_config_yaml: values.base_config_yaml,
        final_target_type: values.final_target_type,
        final_target_group_name:
          values.final_target_type === "group" ? values.final_target_group_name ?? null : null,
        config_id: config?.id ?? null,
        ...groupFields,
      };
      const res = await api.post<PreviewResponse>("/admin/main-configs/preview-draft", payload);
      setPreviewYaml(res.data.yaml);
      setPreviewDiagnostics(res.data.diagnostics);
      setPreviewOpen(true);
    } catch (err) {
      toast.error(errorDetail(err));
    } finally {
      setPreviewing(false);
    }
  };

  // Save
  const submit = async (values: EditorFormValues) => {
    setSaving(true);
    try {
      const groupFields = normalizeGroupFields(values);
      const payload = {
        name: values.name,
        base_config_yaml: values.base_config_yaml,
        enabled: values.enabled,
        final_target_type: values.final_target_type,
        final_target_group_name:
          values.final_target_type === "group" ? values.final_target_group_name ?? null : null,
        ...groupFields,
      };

      if (mode === "edit" && config) {
        await api.put(`/admin/main-configs/${config.id}`, payload);
      } else {
        await api.post("/admin/main-configs", payload);
      }

      toast.success(mode === "edit" ? "Updated" : "Created");
      await onSaved();
      onClose();
    } catch (err) {
      toast.error(errorDetail(err));
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <Dialog open={open} onOpenChange={(o) => { if (!o) onClose(); }}>
        <DialogContent className="sm:max-w-5xl w-[95vw] max-h-[90vh] p-0 flex flex-col">
          <DialogHeader className="px-6 py-4 border-b shrink-0">
            <div className="flex items-center gap-2">
              <DialogTitle>
                {mode === "edit" ? "Edit Config" : mode === "duplicate" ? "Duplicate Config" : "New Config"}
              </DialogTitle>
              <Button variant="outline" size="sm" onClick={() => { setImportSourceId(""); setImportOpen(true); }}>
                <Import className="h-3 w-3 mr-1" /> Import
              </Button>
              <Button variant="outline" size="sm" onClick={() => void handlePreview()} disabled={previewing}>
                <Eye className="h-3 w-3 mr-1" /> {previewing ? "..." : "Preview"}
              </Button>
              <Button variant="outline" size="sm" onClick={onClose}>Cancel</Button>
              <Button size="sm" onClick={form.handleSubmit(submit)} disabled={saving}>
                {saving ? "Saving..." : "Save"}
              </Button>
            </div>
          </DialogHeader>

          <div className="flex-1 min-h-0 overflow-y-auto">
            <form className="p-6 space-y-6">
              {/* Section 1: Main Settings */}
              <div className="space-y-4">
                <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide">Main Settings</h3>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                  <div className="space-y-2">
                    <Label>Name</Label>
                    <Input {...form.register("name", { required: true })} />
                  </div>
                  <div className="flex items-center gap-2 pt-6">
                    <Controller control={form.control} name="enabled" render={({ field }) => (
                      <Switch checked={field.value} onCheckedChange={field.onChange} />
                    )} />
                    <Label>Enabled</Label>
                  </div>
                  <div className="space-y-2">
                    <Label>Final Target</Label>
                    <Controller control={form.control} name="final_target_type" render={({ field }) => (
                      <Select value={field.value} onValueChange={field.onChange}>
                        <SelectTrigger><SelectValue /></SelectTrigger>
                        <SelectContent>
                          <SelectItem value="DIRECT">DIRECT</SelectItem>
                          <SelectItem value="REJECT">REJECT</SelectItem>
                          <SelectItem value="group">Group</SelectItem>
                        </SelectContent>
                      </Select>
                    )} />
                  </div>
                  {finalTargetType === "group" && (
                    <div className="space-y-2">
                      <Label>Final Target Group</Label>
                      <Controller control={form.control} name="final_target_group_name" render={({ field }) => (
                        <Select value={field.value} onValueChange={field.onChange}>
                          <SelectTrigger><SelectValue placeholder="Select group" /></SelectTrigger>
                          <SelectContent>
                            {nonRouteGroupOptions.map((opt) => (
                              <SelectItem key={opt.value} value={opt.value}>{opt.label}</SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      )} />
                    </div>
                  )}
                </div>
                <div className="space-y-2">
                  <Label>Base Config YAML</Label>
                  <Textarea rows={10} {...form.register("base_config_yaml", { required: true })} className="font-mono text-sm" />
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                  <div className="space-y-2">
                    <Label>Test URL</Label>
                    <Input {...form.register("test_url")} placeholder="https://www.gstatic.com/generate_204" />
                  </div>
                  <div className="space-y-2">
                    <Label>Test Interval (sec)</Label>
                    <Input type="number" {...form.register("test_interval_sec", { valueAsNumber: true })} />
                  </div>
                </div>
              </div>

              <Separator />

              {/* Section 2: Filtered Groups */}
              <div className="space-y-3">
                <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide">Filtered Groups</h3>
                <SortableFormList
                  fields={filteredGroupsField.fields}
                  move={(from, to) => { filteredGroupsField.move(from, to); queueFilteredGroupPreview(); }}
                  idPrefix="fg"
                >
                  {(_field, groupIndex, dragHandle) => (
                    <FilteredGroupPanel
                      key={filteredGroupsField.fields[groupIndex]?.id}
                      form={form}
                      groupIndex={groupIndex}
                      dragHandle={dragHandle}
                      subscriptions={subscriptions}
                      filteredGroupPreviews={filteredGroupPreviews}
                      onInsertAbove={() => { filteredGroupsField.insert(groupIndex, { name: "", group_mode: "select", copy_nodes: false, rules: [] }); queueFilteredGroupPreview(); }}
                      onInsertBelow={() => { filteredGroupsField.insert(groupIndex + 1, { name: "", group_mode: "select", copy_nodes: false, rules: [] }); queueFilteredGroupPreview(); }}
                      onRemove={() => { filteredGroupsField.remove(groupIndex); queueFilteredGroupPreview(); }}
                      onPreviewTrigger={queueFilteredGroupPreview}
                    />
                  )}
                </SortableFormList>
                <Button type="button" variant="outline" size="sm" onClick={() => { filteredGroupsField.append({ name: "", group_mode: "select", copy_nodes: false, rules: [] }); queueFilteredGroupPreview(); }}>
                  <Plus className="h-3 w-3 mr-1" /> Add Filtered Group
                </Button>
              </div>

              <Separator />

              {/* Section 3: Manual Groups */}
              <div className="space-y-3">
                <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide">Manual Groups</h3>
                <SortableFormList
                  fields={manualGroupsField.fields}
                  move={manualGroupsField.move}
                  idPrefix="mg"
                >
                  {(_field, groupIndex, dragHandle) => (
                    <ManualGroupPanel
                      key={manualGroupsField.fields[groupIndex]?.id}
                      form={form}
                      groupIndex={groupIndex}
                      dragHandle={dragHandle}
                      filteredGroupOptions={filteredGroupOptions}
                      manualGroupOptions={manualGroupOptions}
                      onInsertAbove={() => manualGroupsField.insert(groupIndex, { name: "", group_mode: "select", members: [] })}
                      onInsertBelow={() => manualGroupsField.insert(groupIndex + 1, { name: "", group_mode: "select", members: [] })}
                      onRemove={() => manualGroupsField.remove(groupIndex)}
                    />
                  )}
                </SortableFormList>
                <Button type="button" variant="outline" size="sm" onClick={() => manualGroupsField.append({ name: "", group_mode: "select", members: [] })}>
                  <Plus className="h-3 w-3 mr-1" /> Add Manual Group
                </Button>
              </div>

              <Separator />

              {/* Section 4: Dialer Overrides */}
              <div className="space-y-3">
                <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide">Dialer Overrides</h3>
                <SortableFormList
                  fields={dialerOverridesField.fields}
                  move={dialerOverridesField.move}
                  idPrefix="do"
                >
                  {(_field, index, dragHandle) => (
                    <div className="p-3 border rounded-md bg-card">
                      <div className="flex items-center gap-2 mb-2">
                        {dragHandle}
                        <span className="text-sm font-medium flex-1">Override #{index + 1}</span>
                        <Button type="button" variant="ghost" size="sm" onClick={() => dialerOverridesField.insert(index, { filtered_group_name: "", dialer_group_name: "" })} title="Insert above">
                          <InsertAboveOutlined className="h-4 w-4" />
                        </Button>
                        <Button type="button" variant="ghost" size="sm" onClick={() => dialerOverridesField.insert(index + 1, { filtered_group_name: "", dialer_group_name: "" })} title="Insert below">
                          <InsertBelowOutlined className="h-4 w-4" />
                        </Button>
                        <Button type="button" variant="ghost" size="sm" onClick={() => dialerOverridesField.remove(index)} className="text-destructive">
                          <Trash2 className="h-3 w-3" />
                        </Button>
                      </div>
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                        <div className="space-y-1">
                          <Label className="text-xs">Filtered Group</Label>
                          <Controller control={form.control} name={`dialer_override_rules.${index}.filtered_group_name`} render={({ field }) => (
                            <Select value={field.value} onValueChange={field.onChange}>
                              <SelectTrigger><SelectValue placeholder="Select" /></SelectTrigger>
                              <SelectContent>
                                {filteredGroupOptions.map((opt) => (
                                  <SelectItem key={opt.value} value={opt.value}>{opt.label}</SelectItem>
                                ))}
                              </SelectContent>
                            </Select>
                          )} />
                        </div>
                        <div className="space-y-1">
                          <Label className="text-xs">Dialer Group</Label>
                          <Controller control={form.control} name={`dialer_override_rules.${index}.dialer_group_name`} render={({ field }) => (
                            <Select value={field.value} onValueChange={field.onChange}>
                              <SelectTrigger><SelectValue placeholder="Select" /></SelectTrigger>
                              <SelectContent>
                                {nonRouteGroupOptions.map((opt) => (
                                  <SelectItem key={opt.value} value={opt.value}>{opt.label}</SelectItem>
                                ))}
                              </SelectContent>
                            </Select>
                          )} />
                        </div>
                      </div>
                    </div>
                  )}
                </SortableFormList>
                <Button type="button" variant="outline" size="sm" onClick={() => dialerOverridesField.append({ filtered_group_name: "", dialer_group_name: "" })}>
                  <Plus className="h-3 w-3 mr-1" /> Add Override
                </Button>
              </div>

              <Separator />

              {/* Section 5: Route Template */}
              <div className="space-y-3">
                <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide">Route Template</h3>
                <Controller control={form.control} name="route_template_id" render={({ field }) => (
                  <Select value={field.value || "__none__"} onValueChange={(v) => { field.onChange(v === "__none__" ? "" : v); form.setValue("slot_mappings", []); }}>
                    <SelectTrigger><SelectValue placeholder="No route template">{field.value ? routeTemplates.find((t) => t.id === field.value)?.name ?? undefined : "No route template"}</SelectValue></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="__none__">No route template</SelectItem>
                      {routeTemplates.map((t) => (
                        <SelectItem key={t.id} value={t.id}>{t.name}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                )} />

                {selectedTemplate && selectedTemplate.slots.length > 0 && (
                  <div className="space-y-2">
                    <Label className="text-sm font-medium">Slot Mappings</Label>
                    {slotMappingsField.fields.map((field, index) => (
                      <div key={field.id} className="grid grid-cols-2 gap-2 items-center">
                        <div className="text-sm font-medium px-2 py-1 bg-muted rounded">
                          {form.getValues(`slot_mappings.${index}.slot_name`)}
                        </div>
                        <Controller control={form.control} name={`slot_mappings.${index}.group_name`} render={({ field: f }) => (
                          <Select value={f.value} onValueChange={f.onChange}>
                            <SelectTrigger><SelectValue placeholder="Select group" /></SelectTrigger>
                            <SelectContent>
                              {nonRouteGroupOptions.map((opt) => (
                                <SelectItem key={opt.value} value={opt.value}>{opt.label}</SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                        )} />
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </form>
          </div>
        </DialogContent>
      </Dialog>

      {/* Import Dialog */}
      <Dialog open={importOpen} onOpenChange={setImportOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Import from Config</DialogTitle>
          </DialogHeader>
          <Alert>
            <AlertTriangle className="h-4 w-4" />
            <AlertDescription>
              This will overwrite all current form fields except name and enabled status.
            </AlertDescription>
          </Alert>
          <Select value={importSourceId || "__none__"} onValueChange={(v: string | null) => setImportSourceId(v === "__none__" || v === null ? "" : v)}>
            <SelectTrigger><SelectValue placeholder="Select config">{importConfigOptions.find((o) => o.value === importSourceId)?.label ?? undefined}</SelectValue></SelectTrigger>
            <SelectContent>
              <SelectItem value="__none__" disabled>Select a config...</SelectItem>
              {importConfigOptions.map((opt) => (
                <SelectItem key={opt.value} value={opt.value}>{opt.label}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <DialogFooter>
            <Button variant="outline" onClick={() => setImportOpen(false)}>Cancel</Button>
            <Button onClick={handleImportConfirm} disabled={!importSourceId}>Import</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Preview Dialog */}
      <Dialog open={previewOpen} onOpenChange={setPreviewOpen}>
        <DialogContent className="max-w-3xl lg:max-w-5xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Draft Preview</DialogTitle>
          </DialogHeader>
          {previewDiagnostics && (
            <div className="space-y-1 text-sm">
              <div><span className="font-medium">Stale subscriptions:</span> {previewDiagnostics.stale_subscription_ids.length > 0 ? previewDiagnostics.stale_subscription_ids.join(", ") : "none"}</div>
              <div><span className="font-medium">Stale rules:</span> {previewDiagnostics.stale_rule_ids.length > 0 ? previewDiagnostics.stale_rule_ids.join(", ") : "none"}</div>
              <div><span className="font-medium">Warnings:</span> {previewDiagnostics.warnings.length > 0 ? previewDiagnostics.warnings.join("; ") : "none"}</div>
            </div>
          )}
          <Textarea readOnly rows={26} value={previewYaml} className="font-mono text-xs" />
        </DialogContent>
      </Dialog>
    </>
  );
}

// --- Sub-components ---

interface FilteredGroupPanelProps {
  form: ReturnType<typeof useForm<EditorFormValues>>;
  groupIndex: number;
  dragHandle: React.ReactNode;
  subscriptions: SubscriptionSourceListItem[];
  filteredGroupPreviews: FilteredGroupPreviewResponse["groups"];
  onInsertAbove: () => void;
  onInsertBelow: () => void;
  onRemove: () => void;
  onPreviewTrigger: () => void;
}

function FilteredGroupPanel({
  form,
  groupIndex,
  dragHandle,
  subscriptions,
  filteredGroupPreviews,
  onInsertAbove,
  onInsertBelow,
  onRemove,
  onPreviewTrigger,
}: FilteredGroupPanelProps) {
  const [isOpen, setIsOpen] = useState(true);
  const rulesField = useFieldArray({ control: form.control, name: `filtered_groups.${groupIndex}.rules` });
  const groupName = form.watch(`filtered_groups.${groupIndex}.name`);

  return (
    <Collapsible open={isOpen} onOpenChange={setIsOpen} className="border rounded-md bg-card">
      <div className="flex items-center gap-2 p-3">
        {dragHandle}
        <CollapsibleTrigger className="flex-1 text-left text-sm font-medium hover:underline">
            {groupName || `Filtered Group #${groupIndex + 1}`}
        </CollapsibleTrigger>
        <Button type="button" variant="ghost" size="sm" onClick={(e) => { e.stopPropagation(); onInsertAbove(); }} title="Insert above">
          <InsertAboveOutlined className="h-4 w-4" />
        </Button>
        <Button type="button" variant="ghost" size="sm" onClick={(e) => { e.stopPropagation(); onInsertBelow(); }} title="Insert below">
          <InsertBelowOutlined className="h-4 w-4" />
        </Button>
        <ConfirmPopover description="Remove this group?" confirmText="Remove" onConfirm={onRemove}>
          <Button type="button" variant="ghost" size="sm" onClick={(e) => e.stopPropagation()} className="text-destructive">
            <Trash2 className="h-3 w-3" />
          </Button>
        </ConfirmPopover>
      </div>
      <CollapsibleContent className="px-3 pb-3 space-y-3">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div className="space-y-1">
            <Label className="text-xs">Name</Label>
            <Input {...form.register(`filtered_groups.${groupIndex}.name`, { required: true, onBlur: () => onPreviewTrigger() })} />
          </div>
          <div className="space-y-1">
            <Label className="text-xs">Mode</Label>
            <div className="flex items-center gap-2">
              <Controller control={form.control} name={`filtered_groups.${groupIndex}.group_mode`} render={({ field }) => (
                <Select value={field.value} onValueChange={field.onChange}>
                  <SelectTrigger className="flex-1"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {groupModeOptions.map((o) => <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>)}
                  </SelectContent>
                </Select>
              )} />
              <Controller control={form.control} name={`filtered_groups.${groupIndex}.copy_nodes`} render={({ field }) => (
                <Switch checked={field.value} onCheckedChange={field.onChange} />
              )} />
              <Label className="text-xs whitespace-nowrap">Copy Nodes</Label>
            </div>
          </div>
        </div>

        {/* Rules */}
        <div className="space-y-2">
          <Label className="text-xs font-medium">Rules</Label>
          <SortableFormList
            fields={rulesField.fields}
            move={(from, to) => { rulesField.move(from, to); onPreviewTrigger(); }}
            idPrefix={`fg-${groupIndex}-rule`}
          >
            {(_field, ruleIndex, ruleDragHandle) => {
              const ruleResult = filteredGroupPreviews[groupIndex]?.rule_results?.[ruleIndex];
              return (
                <div className="p-2 border rounded bg-background space-y-2">
                  <div className="flex items-center gap-2">
                    {ruleDragHandle}
                    <div className="flex-1 flex flex-col sm:flex-row gap-2">
                      <Controller control={form.control} name={`filtered_groups.${groupIndex}.rules.${ruleIndex}.subscription_source_id`} render={({ field }) => (
                        <Select value={field.value} onValueChange={(v) => { field.onChange(v); onPreviewTrigger(); }}>
                          <SelectTrigger className="text-xs sm:min-w-0 sm:flex-[3]"><SelectValue placeholder="Subscription">{subscriptions.find((s) => s.id === field.value)?.name ?? undefined}</SelectValue></SelectTrigger>
                          <SelectContent>
                            {subscriptions.map((s) => (
                              <SelectItem key={s.id} value={s.id}>{s.name}</SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      )} />
                      <Input
                        {...form.register(`filtered_groups.${groupIndex}.rules.${ruleIndex}.regex_pattern`, { onBlur: () => onPreviewTrigger() })}
                        placeholder=".*"
                        className="text-xs sm:min-w-0 sm:flex-[3]"
                      />
                      <Input
                        {...form.register(`filtered_groups.${groupIndex}.rules.${ruleIndex}.regex_flags`, { onBlur: () => onPreviewTrigger() })}
                        placeholder="i"
                        className="text-xs sm:min-w-0 sm:flex-1"
                      />
                    </div>
                    <Button type="button" variant="ghost" size="sm" onClick={() => { rulesField.insert(ruleIndex, { subscription_source_id: "", regex_pattern: ".*", regex_flags: "" }); onPreviewTrigger(); }} title="Insert above">
                      <InsertAboveOutlined className="h-3 w-3" />
                    </Button>
                    <Button type="button" variant="ghost" size="sm" onClick={() => { rulesField.insert(ruleIndex + 1, { subscription_source_id: "", regex_pattern: ".*", regex_flags: "" }); onPreviewTrigger(); }} title="Insert below">
                      <InsertBelowOutlined className="h-3 w-3" />
                    </Button>
                    <Button type="button" variant="ghost" size="sm" onClick={() => { rulesField.remove(ruleIndex); onPreviewTrigger(); }} className="text-destructive">
                      <Trash2 className="h-3 w-3" />
                    </Button>
                  </div>
                  {ruleResult && (
                    <div className="pl-6">
                      {ruleResult.issue ? (
                        <Alert variant="destructive" className="py-1 px-2">
                          <AlertDescription className="text-xs">{ruleResult.issue}</AlertDescription>
                        </Alert>
                      ) : ruleResult.matched_proxy_names.length > 0 ? (
                        <div className="flex flex-wrap gap-1">
                          {ruleResult.matched_proxy_names.map((name) => (
                            <Badge key={name} variant="secondary" className="text-xs">{name}</Badge>
                          ))}
                        </div>
                      ) : (
                        <span className="text-xs text-muted-foreground">No matched proxies</span>
                      )}
                    </div>
                  )}
                </div>
              );
            }}
          </SortableFormList>
          <Button type="button" variant="outline" size="sm" onClick={() => { rulesField.append({ subscription_source_id: "", regex_pattern: ".*", regex_flags: "" }); onPreviewTrigger(); }}>
            <Plus className="h-3 w-3 mr-1" /> Add Rule
          </Button>
        </div>
      </CollapsibleContent>
    </Collapsible>
  );
}

interface ManualGroupPanelProps {
  form: ReturnType<typeof useForm<EditorFormValues>>;
  groupIndex: number;
  dragHandle: React.ReactNode;
  filteredGroupOptions: { label: string; value: string }[];
  manualGroupOptions: { label: string; value: string }[];
  onInsertAbove: () => void;
  onInsertBelow: () => void;
  onRemove: () => void;
}

function ManualGroupPanel({
  form,
  groupIndex,
  dragHandle,
  filteredGroupOptions,
  manualGroupOptions,
  onInsertAbove,
  onInsertBelow,
  onRemove,
}: ManualGroupPanelProps) {
  const [isOpen, setIsOpen] = useState(true);
  const membersField = useFieldArray({ control: form.control, name: `manual_groups.${groupIndex}.members` });
  const groupName = form.watch(`manual_groups.${groupIndex}.name`);

  return (
    <Collapsible open={isOpen} onOpenChange={setIsOpen} className="border rounded-md bg-card">
      <div className="flex items-center gap-2 p-3">
        {dragHandle}
        <CollapsibleTrigger className="flex-1 text-left text-sm font-medium hover:underline">
            {groupName || `Manual Group #${groupIndex + 1}`}
        </CollapsibleTrigger>
        <Button type="button" variant="ghost" size="sm" onClick={(e) => { e.stopPropagation(); onInsertAbove(); }} title="Insert above">
          <InsertAboveOutlined className="h-4 w-4" />
        </Button>
        <Button type="button" variant="ghost" size="sm" onClick={(e) => { e.stopPropagation(); onInsertBelow(); }} title="Insert below">
          <InsertBelowOutlined className="h-4 w-4" />
        </Button>
        <ConfirmPopover description="Remove this group?" confirmText="Remove" onConfirm={onRemove}>
          <Button type="button" variant="ghost" size="sm" onClick={(e) => e.stopPropagation()} className="text-destructive">
            <Trash2 className="h-3 w-3" />
          </Button>
        </ConfirmPopover>
      </div>
      <CollapsibleContent className="px-3 pb-3 space-y-3">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div className="space-y-1">
            <Label className="text-xs">Name</Label>
            <Input {...form.register(`manual_groups.${groupIndex}.name`, { required: true })} />
          </div>
          <div className="space-y-1">
            <Label className="text-xs">Mode</Label>
            <Controller control={form.control} name={`manual_groups.${groupIndex}.group_mode`} render={({ field }) => (
              <Select value={field.value} onValueChange={field.onChange}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {groupModeOptions.map((o) => <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>)}
                </SelectContent>
              </Select>
            )} />
          </div>
        </div>

        {/* Members */}
        <div className="space-y-2">
          <Label className="text-xs font-medium">Members</Label>
          <SortableFormList
            fields={membersField.fields}
            move={membersField.move}
            idPrefix={`mg-${groupIndex}-member`}
          >
            {(_field, memberIndex, memberDragHandle) => {
              const memberType = form.watch(`manual_groups.${groupIndex}.members.${memberIndex}.member_type`);
              const refOptions = memberType === "filtered_group" ? filteredGroupOptions : manualGroupOptions;
              return (
                <div className="p-2 border rounded bg-background">
                  <div className="flex items-center gap-2">
                    {memberDragHandle}
                    <div className="flex-1 flex flex-col sm:flex-row gap-2">
                      <Controller control={form.control} name={`manual_groups.${groupIndex}.members.${memberIndex}.member_type`} render={({ field }) => (
                        <Select value={field.value} onValueChange={(v) => { field.onChange(v); form.setValue(`manual_groups.${groupIndex}.members.${memberIndex}.member_ref`, ""); }}>
                          <SelectTrigger className="text-xs sm:min-w-0 sm:flex-1"><SelectValue>{field.value === "filtered_group" ? "Filtered Group" : field.value === "manual_group" ? "Manual Group" : undefined}</SelectValue></SelectTrigger>
                          <SelectContent>
                            <SelectItem value="filtered_group">Filtered Group</SelectItem>
                            <SelectItem value="manual_group">Manual Group</SelectItem>
                          </SelectContent>
                        </Select>
                      )} />
                      <Controller control={form.control} name={`manual_groups.${groupIndex}.members.${memberIndex}.member_ref`} render={({ field }) => (
                        <Select key={memberType} value={field.value || null} onValueChange={field.onChange}>
                          <SelectTrigger className="text-xs sm:min-w-0 sm:flex-[2]"><SelectValue placeholder="Select" /></SelectTrigger>
                          <SelectContent>
                            {refOptions.map((opt) => (
                              <SelectItem key={opt.value} value={opt.value}>{opt.label}</SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      )} />
                    </div>
                    <Button type="button" variant="ghost" size="sm" onClick={() => membersField.insert(memberIndex, { member_type: "filtered_group", member_ref: "" })} title="Insert above">
                      <InsertAboveOutlined className="h-3 w-3" />
                    </Button>
                    <Button type="button" variant="ghost" size="sm" onClick={() => membersField.insert(memberIndex + 1, { member_type: "filtered_group", member_ref: "" })} title="Insert below">
                      <InsertBelowOutlined className="h-3 w-3" />
                    </Button>
                    <Button type="button" variant="ghost" size="sm" onClick={() => membersField.remove(memberIndex)} className="text-destructive">
                      <Trash2 className="h-3 w-3" />
                    </Button>
                  </div>
                </div>
              );
            }}
          </SortableFormList>
          <Button type="button" variant="outline" size="sm" onClick={() => membersField.append({ member_type: "filtered_group", member_ref: "" })}>
            <Plus className="h-3 w-3 mr-1" /> Add Member
          </Button>
        </div>
      </CollapsibleContent>
    </Collapsible>
  );
}
