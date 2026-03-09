import { useState, useEffect, useCallback, type ReactNode } from "react";
import { arrayMove } from "@dnd-kit/sortable";
import * as yaml from "js-yaml";
import { toast } from "sonner";
import { Plus, RefreshCw, Eye, Download, Trash2, Pencil } from "lucide-react";
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
import { formatBytes, TRAFFIC_COLORS } from "@/utils/format";
import { formatRelativeTime } from "@/utils/time";
import { downloadTextFile } from "@/utils/download";
import type { SubscriptionSource, SubscriptionSourceListItem } from "@/types/api";
import { useForm, Controller } from "react-hook-form";

type SubscriptionFormValues = {
  name: string;
  mode: "remote" | "manual";
  enabled: boolean;
  remote_url: string;
  remote_auth_header: string;
  auto_update: boolean;
  update_interval_sec: number;
  proxy_yaml_object_text: string;
};

const defaultFormValues: SubscriptionFormValues = {
  name: "",
  mode: "remote",
  enabled: true,
  remote_url: "",
  remote_auth_header: "",
  auto_update: false,
  update_interval_sec: 86400,
  proxy_yaml_object_text: "",
};

function hasCachedProxies(item: SubscriptionSourceListItem): boolean {
  return item.cached_proxies_count != null && item.cached_proxies_count > 0;
}

function proxiesToYaml(item: SubscriptionSource): string {
  return yaml.dump(item.cached_proxies_json, { lineWidth: -1 });
}

export default function SubscriptionsPage() {
  const [items, setItems] = useState<SubscriptionSourceListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<SubscriptionSourceListItem | null>(null);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewContent, setPreviewContent] = useState("");
  const [previewTitle, setPreviewTitle] = useState("");

  const form = useForm<SubscriptionFormValues>({ defaultValues: defaultFormValues });
  const mode = form.watch("mode");

  const fetchItems = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.get<SubscriptionSourceListItem[]>("/admin/subscriptions");
      setItems(res.data);
    } catch (err) {
      toast.error(errorDetail(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void fetchItems(); }, [fetchItems]);

  const fetchFullItem = async (id: string): Promise<SubscriptionSource> => {
    const res = await api.get<SubscriptionSource>(`/admin/subscriptions/${id}`);
    return res.data;
  };

  const openCreate = () => {
    setEditing(null);
    form.reset(defaultFormValues);
    setOpen(true);
  };

  const openEdit = async (item: SubscriptionSourceListItem) => {
    setEditing(item);
    if (item.mode === "manual") {
      try {
        const full = await fetchFullItem(item.id);
        form.reset({
          name: item.name,
          mode: item.mode,
          enabled: item.enabled,
          remote_url: item.remote_url ?? "",
          remote_auth_header: item.remote_auth_header ?? "",
          auto_update: item.auto_update,
          update_interval_sec: item.update_interval_sec,
          proxy_yaml_object_text: full.cached_proxies_json
            ? yaml.dump(full.cached_proxies_json[0], { lineWidth: -1 })
            : "",
        });
      } catch (err) {
        toast.error(errorDetail(err));
        return;
      }
    } else {
      form.reset({
        name: item.name,
        mode: item.mode,
        enabled: item.enabled,
        remote_url: item.remote_url ?? "",
        remote_auth_header: item.remote_auth_header ?? "",
        auto_update: item.auto_update,
        update_interval_sec: item.update_interval_sec,
        proxy_yaml_object_text: "",
      });
    }
    setOpen(true);
  };

  const handleSubmit = async (values: SubscriptionFormValues) => {
    try {
      const payload: Record<string, unknown> = {
        name: values.name,
        mode: values.mode,
        enabled: values.enabled,
      };
      if (values.mode === "remote") {
        payload.remote_url = values.remote_url;
        payload.remote_auth_header = values.remote_auth_header || null;
        payload.auto_update = values.auto_update;
        payload.update_interval_sec = values.update_interval_sec;
      } else {
        payload.proxy_yaml_object_text = values.proxy_yaml_object_text;
      }

      let savedId: string;
      const isNew = !editing;
      const urlChanged = editing && values.mode === "remote" && values.remote_url !== (editing.remote_url ?? "");

      if (editing) {
        const res = await api.put<SubscriptionSource>(`/admin/subscriptions/${editing.id}`, payload);
        savedId = res.data.id;
      } else {
        const res = await api.post<SubscriptionSource>("/admin/subscriptions", payload);
        savedId = res.data.id;
      }

      const shouldRefresh = values.mode === "remote" && (isNew || urlChanged);
      if (shouldRefresh) {
        try {
          await api.post(`/admin/subscriptions/${savedId}/refresh`);
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

  const handleDelete = async (item: SubscriptionSourceListItem) => {
    try {
      await api.delete(`/admin/subscriptions/${item.id}`);
      toast.success("Deleted");
      await fetchItems();
    } catch (err) {
      toast.error(errorDetail(err));
    }
  };

  const handleRefresh = async (item: SubscriptionSourceListItem) => {
    try {
      await api.post(`/admin/subscriptions/${item.id}/refresh`);
      toast.success("Refreshed");
      await fetchItems();
    } catch (err) {
      toast.error(errorDetail(err));
    }
  };

  const openPreview = async (item: SubscriptionSourceListItem) => {
    try {
      const full = await fetchFullItem(item.id);
      setPreviewTitle(item.name);
      setPreviewContent(proxiesToYaml(full));
      setPreviewOpen(true);
    } catch (err) {
      toast.error(errorDetail(err));
    }
  };

  const handleDownload = async (item: SubscriptionSourceListItem) => {
    try {
      const full = await fetchFullItem(item.id);
      downloadTextFile(proxiesToYaml(full), `${item.name}_proxies.yaml`, "text/yaml");
    } catch (err) {
      toast.error(errorDetail(err));
    }
  };

  const handleReorder = async (oldIndex: number, newIndex: number) => {
    const reordered = arrayMove(items, oldIndex, newIndex);
    setItems(reordered);
    try {
      await api.put("/admin/subscriptions/reorder", {
        items: reordered.map((item, i) => ({ id: item.id, position: i + 1 })),
      });
      toast.success("Reorder saved");
    } catch (err) {
      toast.error(errorDetail(err));
      await fetchItems();
    }
  };

  const renderCard = (item: SubscriptionSourceListItem, dragHandle: ReactNode) => {
    const info = item.subscription_userinfo_json;
    const hasTraffic = info && info.total;

    return (
      <Card key={item.id} className="flex flex-col">
        <CardHeader className="pb-2">
          <div className="flex items-center gap-2">
            {dragHandle}
            <CardTitle className="text-base flex-1 truncate">{item.name}</CardTitle>
          </div>
          <div className="flex flex-wrap gap-1 mt-1">
            <Badge variant="outline">{item.mode}</Badge>
            <Badge
              variant={item.last_status === "ok" ? "default" : item.last_status === "error" ? "destructive" : "secondary"}
              className={item.last_status === "ok" ? "bg-green-600" : ""}
            >
              {item.last_status}
            </Badge>
            {hasCachedProxies(item) && (
              <Badge variant="secondary">{item.cached_proxies_count} proxies</Badge>
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
          {hasTraffic && (() => {
            const upload = info.upload ?? 0;
            const download = info.download ?? 0;
            const total = info.total!;
            const uploadPct = Math.min((upload / total) * 100, 100);
            const totalUsedPct = Math.min(((upload + download) / total) * 100, 100);
            return (
              <div className="space-y-1">
                <div className="w-full h-2 bg-muted rounded-full overflow-hidden relative">
                  <div
                    className="absolute h-full rounded-full"
                    style={{ width: `${totalUsedPct}%`, backgroundColor: TRAFFIC_COLORS.download }}
                  />
                  <div
                    className="absolute h-full rounded-full"
                    style={{ width: `${uploadPct}%`, backgroundColor: TRAFFIC_COLORS.upload }}
                  />
                </div>
                <div className="text-xs text-muted-foreground">
                  U: {formatBytes(upload)} / D: {formatBytes(download)} / {formatBytes(total)}
                </div>
                {info.expire ? (
                  <div className="text-xs text-muted-foreground">
                    Expires: {new Date(info.expire * 1000).toLocaleDateString()}
                  </div>
                ) : null}
              </div>
            );
          })()}
          <div className="flex flex-wrap gap-1 pt-2">
            <Button variant="outline" size="sm" title="Edit" onClick={() => void openEdit(item)}>
              <Pencil className="h-3 w-3" />
            </Button>
            {item.mode === "remote" && (
              <Button variant="outline" size="sm" title="Refresh" onClick={() => void handleRefresh(item)}>
                <RefreshCw className="h-3 w-3" />
              </Button>
            )}
            <Button
              variant="outline"
              size="sm"
              title="Preview"
              disabled={!hasCachedProxies(item)}
              onClick={() => void openPreview(item)}
            >
              <Eye className="h-3 w-3" />
            </Button>
            <Button
              variant="outline"
              size="sm"
              title="Download"
              disabled={!hasCachedProxies(item)}
              onClick={() => void handleDownload(item)}
            >
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
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-end gap-2">
        <Button variant="outline" size="sm" onClick={() => void fetchItems()}>
          <RefreshCw className="h-4 w-4" />
        </Button>
        <Button size="sm" onClick={openCreate}>
          <Plus className="h-4 w-4 mr-1" /> New Subscription
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
            <DialogTitle>{editing ? "Edit Subscription" : "New Subscription"}</DialogTitle>
          </DialogHeader>
          <form onSubmit={form.handleSubmit(handleSubmit)} className="space-y-4">
            <div className="space-y-2">
              <Label>Name</Label>
              <Input {...form.register("name", { required: "Name is required" })} />
              {form.formState.errors.name && <p className="text-sm text-destructive">{form.formState.errors.name.message}</p>}
            </div>

            <div className="space-y-2">
              <Label>Mode</Label>
              <Controller
                control={form.control}
                name="mode"
                render={({ field }) => (
                  <Select value={field.value} onValueChange={field.onChange}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="remote">Remote</SelectItem>
                      <SelectItem value="manual">Manual</SelectItem>
                    </SelectContent>
                  </Select>
                )}
              />
            </div>

            <div className="flex items-center gap-2">
              <Controller
                control={form.control}
                name="enabled"
                render={({ field }) => (
                  <Switch checked={field.value} onCheckedChange={field.onChange} />
                )}
              />
              <Label>Enabled</Label>
            </div>

            {mode === "remote" && (
              <>
                <div className="space-y-2">
                  <Label>Remote URL</Label>
                  <Input {...form.register("remote_url", { required: "URL is required" })} />
                  {form.formState.errors.remote_url && <p className="text-sm text-destructive">{form.formState.errors.remote_url.message}</p>}
                </div>
                <div className="space-y-2">
                  <Label>Auth Header</Label>
                  <Input {...form.register("remote_auth_header")} placeholder="token xxxxxx" />
                </div>
                <div className="flex items-center gap-2">
                  <Controller
                    control={form.control}
                    name="auto_update"
                    render={({ field }) => (
                      <Switch checked={field.value} onCheckedChange={field.onChange} />
                    )}
                  />
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
                <Label>Proxy YAML</Label>
                <Textarea
                  rows={10}
                  {...form.register("proxy_yaml_object_text", { required: "Proxy YAML is required" })}
                  placeholder={"name: my-proxy\ntype: ss\nserver: example.com\nport: 443\ncipher: chacha20-ietf-poly1305\npassword: secret"}
                />
                {form.formState.errors.proxy_yaml_object_text && <p className="text-sm text-destructive">{form.formState.errors.proxy_yaml_object_text.message}</p>}
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
        <DialogContent className="max-w-2xl lg:max-w-4xl max-h-[90vh]">
          <DialogHeader>
            <DialogTitle>Preview: {previewTitle}</DialogTitle>
          </DialogHeader>
          <Textarea readOnly rows={20} value={previewContent} className="font-mono text-xs" />
        </DialogContent>
      </Dialog>
    </div>
  );
}
