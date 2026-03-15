import { useState, useEffect, useCallback, type ReactNode } from "react";
import { arrayMove } from "@dnd-kit/sortable";
import * as yaml from "js-yaml";
import { toast } from "sonner";
import { Plus, RefreshCw, Eye, Download, Trash2, Pencil, ExternalLink } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { ConfirmPopover } from "@/components/ui/confirm-popover";
import CardGrid from "@/components/CardGrid";
import api, { errorDetail } from "@/utils/api";
import { formatRelativeTime } from "@/utils/time";
import { downloadTextFile } from "@/utils/download";
import type { RuleSource, RuleSourceListItem } from "@/types/api";
import { useForm, Controller } from "react-hook-form";

type RuleFormValues = {
  name: string;
  mode: "remote" | "manual";
  behavior: "classical" | "domain" | "ipcidr";
  enabled: boolean;
  remote_url: string;
  auto_update: boolean;
  update_interval_sec: number;
  payload_lines_text: string;
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
  if (!text) return [];
  return text.split("\n").map((line) => line.trim()).filter((line) => line.length > 0);
}

const behaviorPlaceholders: Record<string, string> = {
  classical: "DOMAIN-SUFFIX,google.com\nDOMAIN-KEYWORD,google\nDOMAIN,ad.com\nSRC-IP-CIDR,192.168.1.201/32\nIP-CIDR,127.0.0.0/8\nGEOIP,CN\nDST-PORT,80\nSRC-PORT,7777\nIP-CIDR,1.1.1.1/32,no-resolve",
  domain: ".google.com\n+.youtube.com\n*.github.com\nexample.com\n\nWildcards:\n*  matches one level only\n+  matches like DOMAIN-SUFFIX\n.  matches subdomains only",
  ipcidr: "192.168.1.0/24\n10.0.0.1/32",
};

function hasCachedPayload(item: RuleSourceListItem): boolean {
  return item.cached_payload_lines_count != null && item.cached_payload_lines_count > 0;
}

export default function RulesPage() {
  const [items, setItems] = useState<RuleSourceListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<RuleSourceListItem | null>(null);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewContent, setPreviewContent] = useState("");
  const [previewTitle, setPreviewTitle] = useState("");

  const form = useForm<RuleFormValues>({ defaultValues: defaultFormValues });
  const mode = form.watch("mode");
  const behavior = form.watch("behavior");

  const fetchItems = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.get<RuleSourceListItem[]>("/admin/rules");
      setItems(res.data);
    } catch (err) {
      toast.error(errorDetail(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void fetchItems(); }, [fetchItems]);

  const fetchFullItem = async (id: string): Promise<RuleSource> => {
    const res = await api.get<RuleSource>(`/admin/rules/${id}`);
    return res.data;
  };

  const openCreate = () => {
    setEditing(null);
    form.reset(defaultFormValues);
    setOpen(true);
  };

  const openEdit = async (item: RuleSourceListItem) => {
    setEditing(item);
    if (item.mode === "manual") {
      try {
        const full = await fetchFullItem(item.id);
        form.reset({
          name: item.name,
          mode: item.mode,
          behavior: item.behavior,
          enabled: item.enabled,
          remote_url: item.remote_url ?? "",
          auto_update: item.auto_update,
          update_interval_sec: item.update_interval_sec,
          payload_lines_text: full.cached_payload_lines_json?.join("\n") ?? "",
        });
      } catch (err) {
        toast.error(errorDetail(err));
        return;
      }
    } else {
      form.reset({
        name: item.name,
        mode: item.mode,
        behavior: item.behavior,
        enabled: item.enabled,
        remote_url: item.remote_url ?? "",
        auto_update: item.auto_update,
        update_interval_sec: item.update_interval_sec,
        payload_lines_text: "",
      });
    }
    setOpen(true);
  };

  const onSubmit = async (values: RuleFormValues) => {
    try {
      const payload: Record<string, unknown> = {
        name: values.name,
        mode: values.mode,
        behavior: values.behavior,
        enabled: values.enabled,
      };
      if (values.mode === "remote") {
        payload.remote_url = values.remote_url;
        payload.auto_update = values.auto_update;
        payload.update_interval_sec = values.update_interval_sec;
      } else {
        payload.payload_lines = linesTextToArray(values.payload_lines_text);
      }

      let savedId: string;
      const isNew = !editing;
      const urlChanged = editing && values.mode === "remote" && values.remote_url !== (editing.remote_url ?? "");

      if (editing) {
        const res = await api.put<RuleSource>(`/admin/rules/${editing.id}`, payload);
        savedId = res.data.id;
      } else {
        const res = await api.post<RuleSource>("/admin/rules", payload);
        savedId = res.data.id;
      }

      const shouldRefresh = values.mode === "remote" && (isNew || urlChanged);
      if (shouldRefresh) {
        try {
          await api.post(`/admin/rules/${savedId}/refresh`);
          toast.success(editing ? "Updated & refreshed" : "Created & refreshed");
        } catch (refreshErr) {
          toast.warning(`${editing ? "Updated" : "Created"}, but refresh failed: ${errorDetail(refreshErr)}`);
        }
      } else {
        toast.success(editing ? "Updated" : "Created");
      }

      setOpen(false);
      await fetchItems();
    } catch (err) {
      toast.error(errorDetail(err));
    }
  };

  const handleDelete = async (item: RuleSourceListItem) => {
    try {
      await api.delete(`/admin/rules/${item.id}`);
      toast.success("Deleted");
      await fetchItems();
    } catch (err) {
      toast.error(errorDetail(err));
    }
  };

  const handleRefresh = async (item: RuleSourceListItem) => {
    try {
      await api.post(`/admin/rules/${item.id}/refresh`);
      toast.success("Refreshed");
      await fetchItems();
    } catch (err) {
      toast.error(errorDetail(err));
    }
  };

  const openPreview = async (item: RuleSourceListItem) => {
    try {
      const full = await fetchFullItem(item.id);
      setPreviewTitle(item.name);
      setPreviewContent(yaml.dump({ payload: full.cached_payload_lines_json }, { lineWidth: -1 }));
      setPreviewOpen(true);
    } catch (err) {
      toast.error(errorDetail(err));
    }
  };

  const handleDownload = async (item: RuleSourceListItem) => {
    try {
      const full = await fetchFullItem(item.id);
      downloadTextFile(
        yaml.dump({ payload: full.cached_payload_lines_json }, { lineWidth: -1 }),
        `${item.name}_rules.yaml`,
        "text/yaml"
      );
    } catch (err) {
      toast.error(errorDetail(err));
    }
  };

  const handleReorder = async (oldIndex: number, newIndex: number) => {
    const reordered = arrayMove(items, oldIndex, newIndex);
    setItems(reordered);
    try {
      await api.put("/admin/rules/reorder", {
        items: reordered.map((item, i) => ({ id: item.id, position: i + 1 })),
      });
      toast.success("Reorder saved");
    } catch (err) {
      toast.error(errorDetail(err));
      await fetchItems();
    }
  };

  const renderCard = (item: RuleSourceListItem, dragHandle: ReactNode) => (
    <Card key={item.id} className="flex flex-col">
      <CardHeader className="pb-2">
        <div className="flex items-center gap-2">
          {dragHandle}
          <CardTitle className="text-base flex-1 truncate">{item.name}</CardTitle>
        </div>
        <div className="flex flex-wrap gap-1 mt-1">
          <Badge variant="outline">{item.mode}</Badge>
          <Badge variant="outline" className="border-blue-400 text-blue-600">{item.behavior}</Badge>
          <Badge
            variant={item.last_status === "ok" ? "default" : item.last_status === "error" ? "destructive" : "secondary"}
            className={item.last_status === "ok" ? "bg-green-600" : ""}
          >
            {item.last_status}
          </Badge>
          {hasCachedPayload(item) && (
            <Badge variant="secondary">{item.cached_payload_lines_count} rules</Badge>
          )}
        </div>
      </CardHeader>
      <CardContent className="flex-1 space-y-2 text-sm">
        {item.last_refresh_at && (
          <div className="text-muted-foreground">
            <Tooltip>
              <TooltipTrigger>
                <span>Refreshed: {formatRelativeTime(item.last_refresh_at)}</span>
              </TooltipTrigger>
              <TooltipContent>{new Date(item.last_refresh_at).toLocaleString()}</TooltipContent>
            </Tooltip>
          </div>
        )}
        {item.next_refresh_at && (
          <div className="text-muted-foreground">
            <Tooltip>
              <TooltipTrigger>
                <span>Next: {formatRelativeTime(item.next_refresh_at)}</span>
              </TooltipTrigger>
              <TooltipContent>{new Date(item.next_refresh_at).toLocaleString()}</TooltipContent>
            </Tooltip>
          </div>
        )}
        <div className="flex flex-wrap gap-1 pt-2">
          <Button variant="outline" size="sm" title="Edit" onClick={() => void openEdit(item)}>
            <Pencil className="h-3 w-3" />
          </Button>
          {item.mode === "remote" && (
            <Button variant="outline" size="sm" title="Refresh" onClick={() => void handleRefresh(item)}>
              <RefreshCw className="h-3 w-3" />
            </Button>
          )}
          <Button variant="outline" size="sm" title="Preview" disabled={!hasCachedPayload(item)} onClick={() => void openPreview(item)}>
            <Eye className="h-3 w-3" />
          </Button>
          <Button variant="outline" size="sm" title="Download" disabled={!hasCachedPayload(item)} onClick={() => void handleDownload(item)}>
            <Download className="h-3 w-3" />
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
        <Button variant="outline" size="sm" onClick={() => void fetchItems()}>
          <RefreshCw className="h-4 w-4" />
        </Button>
        <a href="https://github.com/MetaCubeX/meta-rules-dat/tree/meta/geo/geosite" target="_blank" rel="noreferrer">
          <Button variant="outline" size="sm">
            <ExternalLink className="h-4 w-4 mr-1" /> GeoSite Rules
          </Button>
        </a>
        <Button size="sm" onClick={openCreate}>
          <Plus className="h-4 w-4 mr-1" /> New Rule
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
        <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{editing ? "Edit Rule" : "New Rule"}</DialogTitle>
          </DialogHeader>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
            <div className="space-y-2">
              <Label>Name</Label>
              <Input {...form.register("name", { required: "Name is required" })} />
              {form.formState.errors.name && <p className="text-sm text-destructive">{form.formState.errors.name.message}</p>}
            </div>

            <div className="space-y-2">
              <Label>Mode</Label>
              <Controller control={form.control} name="mode" render={({ field }) => (
                <Select value={field.value} onValueChange={field.onChange}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="remote">Remote</SelectItem>
                    <SelectItem value="manual">Manual</SelectItem>
                  </SelectContent>
                </Select>
              )} />
            </div>

            <div className="space-y-2">
              <Label>Behavior</Label>
              <Controller control={form.control} name="behavior" render={({ field }) => (
                <Select value={field.value} onValueChange={field.onChange}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="classical">classical</SelectItem>
                    <SelectItem value="domain">domain</SelectItem>
                    <SelectItem value="ipcidr">ipcidr</SelectItem>
                  </SelectContent>
                </Select>
              )} />
            </div>

            <div className="flex items-center gap-2">
              <Controller control={form.control} name="enabled" render={({ field }) => (
                <Switch checked={field.value} onCheckedChange={field.onChange} />
              )} />
              <Label>Enabled</Label>
            </div>

            {mode === "remote" && (
              <>
                <div className="space-y-2">
                  <Label>Remote URL</Label>
                  <Input {...form.register("remote_url", { required: "URL is required" })} />
                  {form.formState.errors.remote_url && <p className="text-sm text-destructive">{form.formState.errors.remote_url.message}</p>}
                </div>
                <div className="flex items-center gap-2">
                  <Controller control={form.control} name="auto_update" render={({ field }) => (
                    <Switch checked={field.value} onCheckedChange={field.onChange} />
                  )} />
                  <Label>Auto Update</Label>
                </div>
                <div className="space-y-2">
                  <Label>Update Interval (seconds)</Label>
                  <Input type="number" {...form.register("update_interval_sec", { valueAsNumber: true, min: 60 })} />
                </div>
              </>
            )}

            {mode === "manual" && (
              <div className="space-y-2">
                <Label>Payload Lines</Label>
                <Textarea
                  rows={10}
                  {...form.register("payload_lines_text", { required: "Payload is required" })}
                  placeholder={behaviorPlaceholders[behavior] ?? ""}
                />
                {form.formState.errors.payload_lines_text && <p className="text-sm text-destructive">{form.formState.errors.payload_lines_text.message}</p>}
              </div>
            )}

            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setOpen(false)}>Cancel</Button>
              <Button type="submit">Save</Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* Preview Dialog */}
      <Dialog open={previewOpen} onOpenChange={setPreviewOpen}>
        <DialogContent className="max-w-2xl lg:max-w-4xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Preview: {previewTitle}</DialogTitle>
          </DialogHeader>
          <Textarea readOnly rows={20} value={previewContent} className="font-mono text-xs" />
        </DialogContent>
      </Dialog>
    </div>
  );
}
