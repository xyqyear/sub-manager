import { useState, useEffect, useCallback, useMemo, type ReactNode } from "react";
import { arrayMove } from "@dnd-kit/sortable";
import { toast } from "sonner";
import { Plus, RefreshCw, Trash2, Pencil } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Separator } from "@/components/ui/separator";
import { ConfirmPopover } from "@/components/ui/confirm-popover";
import CardGrid from "@/components/CardGrid";
import SortableFormList from "@/components/dnd/SortableFormList";
import { InsertAboveOutlined, InsertBelowOutlined } from "@/components/icons";
import api, { errorDetail } from "@/utils/api";
import type { RouteTemplate, RuleSourceListItem } from "@/types/api";
import { useForm, useFieldArray, Controller } from "react-hook-form";

type TemplateFormValues = {
  name: string;
  slots: { name: string }[];
  bindings: {
    binding_name: string;
    rule_source_id: string;
    default_target: string;
    no_resolve: boolean;
  }[];
};

const defaultFormValues: TemplateFormValues = {
  name: "",
  slots: [],
  bindings: [],
};

export default function RouteTemplatesPage() {
  const [items, setItems] = useState<RouteTemplate[]>([]);
  const [rules, setRules] = useState<RuleSourceListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<RouteTemplate | null>(null);

  const form = useForm<TemplateFormValues>({ defaultValues: defaultFormValues });
  const slotsField = useFieldArray({ control: form.control, name: "slots" });
  const bindingsField = useFieldArray({ control: form.control, name: "bindings" });
  const slotsWatch = form.watch("slots");

  const slotTargetOptions = useMemo(() => [
    { label: "DIRECT", value: "DIRECT" },
    { label: "REJECT", value: "REJECT" },
    ...(slotsWatch ?? [])
      .filter((s) => s?.name)
      .map((s) => ({ label: s.name, value: s.name })),
  ], [slotsWatch]);

  const fetchAll = useCallback(async () => {
    setLoading(true);
    try {
      const [templatesRes, rulesRes] = await Promise.all([
        api.get<RouteTemplate[]>("/admin/route-templates"),
        api.get<RuleSourceListItem[]>("/admin/rules"),
      ]);
      setItems(templatesRes.data);
      setRules(rulesRes.data);
    } catch (err) {
      toast.error(errorDetail(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void fetchAll(); }, [fetchAll]);

  const openCreate = () => {
    setEditing(null);
    form.reset(defaultFormValues);
    setOpen(true);
  };

  const openEdit = (item: RouteTemplate) => {
    setEditing(item);
    form.reset({
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

  const onSubmit = async (values: TemplateFormValues) => {
    try {
      const payload = {
        name: values.name,
        slots: values.slots.map((s, i) => ({ name: s.name, position: i + 1 })),
        bindings: values.bindings.map((b, i) => ({
          position: i + 1,
          binding_name: b.binding_name?.trim() || (rules.find((r) => r.id === b.rule_source_id)?.name ?? ""),
          rule_source_id: b.rule_source_id,
          default_target: b.default_target,
          no_resolve: Boolean(b.no_resolve),
        })),
      };

      if (editing) {
        await api.put(`/admin/route-templates/${editing.id}`, payload);
        toast.success("Updated");
      } else {
        await api.post("/admin/route-templates", payload);
        toast.success("Created");
      }

      setOpen(false);
      await fetchAll();
    } catch (err) {
      toast.error(errorDetail(err));
    }
  };

  const handleDelete = async (item: RouteTemplate) => {
    try {
      await api.delete(`/admin/route-templates/${item.id}`);
      toast.success("Deleted");
      await fetchAll();
    } catch (err) {
      toast.error(errorDetail(err));
    }
  };

  const handleReorder = async (oldIndex: number, newIndex: number) => {
    const reordered = arrayMove(items, oldIndex, newIndex);
    setItems(reordered);
    try {
      await api.put("/admin/route-templates/reorder", {
        items: reordered.map((item, i) => ({ id: item.id, position: i + 1 })),
      });
    } catch (err) {
      toast.error(errorDetail(err));
      await fetchAll();
    }
  };

  const renderCard = (item: RouteTemplate, dragHandle: ReactNode) => (
    <Card key={item.id} className="flex flex-col">
      <CardHeader className="pb-2">
        <div className="flex items-center gap-2">
          {dragHandle}
          <CardTitle className="text-base flex-1 truncate">{item.name}</CardTitle>
        </div>
        <div className="flex flex-wrap gap-1 mt-1">
          <Badge variant="secondary">{item.slots.length} slots</Badge>
          <Badge variant="secondary">{item.bindings.length} bindings</Badge>
        </div>
      </CardHeader>
      <CardContent className="flex-1">
        <div className="flex flex-wrap gap-1 pt-2">
          <Button variant="outline" size="sm" title="Edit" onClick={() => openEdit(item)}>
            <Pencil className="h-3 w-3" />
          </Button>
          <ConfirmPopover description={`Delete "${item.name}"?`} onConfirm={() => void handleDelete(item)}>
            <Button variant="destructive" size="sm">
              <Trash2 className="h-3 w-3" />
            </Button>
          </ConfirmPopover>
        </div>
      </CardContent>
    </Card>
  );

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-end gap-2">
        <Button variant="outline" size="sm" onClick={() => void fetchAll()}>
          <RefreshCw className="h-4 w-4" />
        </Button>
        <Button size="sm" onClick={openCreate}>
          <Plus className="h-4 w-4 mr-1" /> New Template
        </Button>
      </div>

      <CardGrid
        items={items}
        loading={loading}
        rowKey={(item) => item.id}
        renderCard={renderCard}
        onReorder={handleReorder}
      />

      {/* Create / Edit Dialog */}
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="sm:max-w-4xl w-[90vw] max-h-[90vh] p-0 flex flex-col">
          <DialogHeader className="px-6 py-4 border-b shrink-0">
            <DialogTitle>{editing ? "Edit Template" : "New Template"}</DialogTitle>
          </DialogHeader>
          <div className="flex-1 min-h-0 overflow-y-auto">
            <form onSubmit={form.handleSubmit(onSubmit)} className="p-6 space-y-4">
              <div className="space-y-2">
                <Label>Name</Label>
                <Input {...form.register("name", { required: "Name is required" })} />
                {form.formState.errors.name && <p className="text-sm text-destructive">{form.formState.errors.name.message}</p>}
              </div>

              <Separator />

              {/* Slots */}
              <div className="space-y-2">
                <Label className="text-base font-medium">Slots</Label>
                <SortableFormList
                  fields={slotsField.fields}
                  move={slotsField.move}
                  idPrefix="slot"
                >
                  {(_field, index, dragHandle) => (
                    <div className="flex items-center gap-2 p-2 border rounded-md bg-card">
                      {dragHandle}
                      <Input
                        {...form.register(`slots.${index}.name`, { required: true })}
                        placeholder="Slot name"
                        className="flex-1"
                      />
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        onClick={() => slotsField.insert(index, { name: "" })}
                        title="Insert above"
                      >
                        <InsertAboveOutlined className="h-4 w-4" />
                      </Button>
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        onClick={() => slotsField.insert(index + 1, { name: "" })}
                        title="Insert below"
                      >
                        <InsertBelowOutlined className="h-4 w-4" />
                      </Button>
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        onClick={() => slotsField.remove(index)}
                        className="text-destructive"
                      >
                        <Trash2 className="h-3 w-3" />
                      </Button>
                    </div>
                  )}
                </SortableFormList>
                <Button type="button" variant="outline" size="sm" onClick={() => slotsField.append({ name: "" })}>
                  <Plus className="h-3 w-3 mr-1" /> Add Slot
                </Button>
              </div>

              <Separator />

              {/* Bindings */}
              <div className="space-y-2">
                <Label className="text-base font-medium">Bindings</Label>
                <SortableFormList
                  fields={bindingsField.fields}
                  move={bindingsField.move}
                  idPrefix="binding"
                >
                  {(_field, index, dragHandle) => {
                    const ruleSourceId = form.watch(`bindings.${index}.rule_source_id`);
                    const ruleSource = rules.find((r) => r.id === ruleSourceId);
                    const ruleName = ruleSource?.name;

                    return (
                      <div className="p-3 border rounded-md bg-card flex flex-col gap-2 lg:flex-row lg:items-center">
                        <div className="flex items-center gap-2 lg:contents">
                          {dragHandle}
                          <span className="text-sm font-medium flex-1 lg:hidden">Binding #{index + 1}</span>
                          <div className="flex items-center gap-1 lg:order-last">
                            <Button type="button" variant="ghost" size="sm" onClick={() => bindingsField.insert(index, { binding_name: "", rule_source_id: "", default_target: "DIRECT", no_resolve: false })} title="Insert above">
                              <InsertAboveOutlined className="h-4 w-4" />
                            </Button>
                            <Button type="button" variant="ghost" size="sm" onClick={() => bindingsField.insert(index + 1, { binding_name: "", rule_source_id: "", default_target: "DIRECT", no_resolve: false })} title="Insert below">
                              <InsertBelowOutlined className="h-4 w-4" />
                            </Button>
                            <Button type="button" variant="ghost" size="sm" onClick={() => bindingsField.remove(index)} className="text-destructive">
                              <Trash2 className="h-3 w-3" />
                            </Button>
                          </div>
                        </div>
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 lg:contents">
                          <div className="space-y-1 lg:space-y-0 lg:flex-[3_1_0%] lg:min-w-[140px]">
                            <Label className="text-xs lg:sr-only">Rule Source</Label>
                            <Controller
                              control={form.control}
                              name={`bindings.${index}.rule_source_id`}
                              rules={{ required: true }}
                              render={({ field }) => (
                                <Select value={field.value} onValueChange={field.onChange}>
                                  <SelectTrigger className="w-full"><SelectValue placeholder="Select rule">{ruleSource ? `${ruleSource.name} (${ruleSource.behavior})` : undefined}</SelectValue></SelectTrigger>
                                  <SelectContent>
                                    {rules.map((r) => (
                                      <SelectItem key={r.id} value={r.id}>
                                        {r.name} ({r.behavior})
                                      </SelectItem>
                                    ))}
                                  </SelectContent>
                                </Select>
                              )}
                            />
                          </div>
                          <div className="space-y-1 lg:space-y-0 lg:flex-[2_1_0%] lg:min-w-[100px]">
                            <Label className="text-xs lg:sr-only">Binding Name</Label>
                            <Input
                              {...form.register(`bindings.${index}.binding_name`)}
                              placeholder={ruleName || "Same as rule source"}
                            />
                          </div>
                          <div className="space-y-1 lg:space-y-0 lg:flex-[2_1_0%] lg:min-w-[100px]">
                            <Label className="text-xs lg:sr-only">Default Target</Label>
                            <Controller
                              control={form.control}
                              name={`bindings.${index}.default_target`}
                              rules={{ required: true }}
                              render={({ field }) => (
                                <Select value={field.value} onValueChange={field.onChange}>
                                  <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                                  <SelectContent>
                                    {slotTargetOptions.map((opt) => (
                                      <SelectItem key={opt.value} value={opt.value}>{opt.label}</SelectItem>
                                    ))}
                                  </SelectContent>
                                </Select>
                              )}
                            />
                          </div>
                          <div className="flex items-center gap-2 pt-5 lg:pt-0 lg:flex-none">
                            <Controller
                              control={form.control}
                              name={`bindings.${index}.no_resolve`}
                              render={({ field }) => (
                                <Switch checked={field.value} onCheckedChange={field.onChange} />
                              )}
                            />
                            <Label className="text-xs">No Resolve</Label>
                          </div>
                        </div>
                      </div>
                    );
                  }}
                </SortableFormList>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => bindingsField.append({ binding_name: "", rule_source_id: "", default_target: "DIRECT", no_resolve: false })}
                >
                  <Plus className="h-3 w-3 mr-1" /> Add Binding
                </Button>
              </div>
            </form>
          </div>
          <DialogFooter className="mx-0 mb-0 px-6 py-4 shrink-0">
            <Button type="button" variant="outline" onClick={() => setOpen(false)}>Cancel</Button>
            <Button onClick={form.handleSubmit(onSubmit)}>Save</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
