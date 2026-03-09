import { useState, useEffect, useCallback, type ReactNode } from "react";
import { arrayMove } from "@dnd-kit/sortable";
import { toast } from "sonner";
import { Plus, RefreshCw, Trash2, Pencil, Copy, Eye, Link } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { ConfirmPopover } from "@/components/ui/confirm-popover";
import CardGrid from "@/components/CardGrid";
import MainConfigEditorDrawer from "@/pages/main-configs/MainConfigEditorDrawer";
import api, { errorDetail } from "@/utils/api";
import type {
  MainConfig,
  SubscriptionSourceListItem,
  RouteTemplate,
  PreviewResponse,
} from "@/types/api";

type EditorMode = "create" | "edit" | "duplicate";

export default function MainConfigsPage() {
  const [items, setItems] = useState<MainConfig[]>([]);
  const [subscriptions, setSubscriptions] = useState<SubscriptionSourceListItem[]>([]);
  const [routeTemplates, setRouteTemplates] = useState<RouteTemplate[]>([]);
  const [loading, setLoading] = useState(true);
  const [editorOpen, setEditorOpen] = useState(false);
  const [editing, setEditing] = useState<MainConfig | null>(null);
  const [editorMode, setEditorMode] = useState<EditorMode>("create");
  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewYaml, setPreviewYaml] = useState("");
  const [previewDiagnostics, setPreviewDiagnostics] = useState<PreviewResponse["diagnostics"] | null>(null);

  const fetchAll = useCallback(async () => {
    setLoading(true);
    try {
      const [configsRes, subsRes, templatesRes] = await Promise.all([
        api.get<MainConfig[]>("/admin/main-configs"),
        api.get<SubscriptionSourceListItem[]>("/admin/subscriptions"),
        api.get<RouteTemplate[]>("/admin/route-templates"),
      ]);
      setItems(configsRes.data);
      setSubscriptions(subsRes.data);
      setRouteTemplates(templatesRes.data);
    } catch (err) {
      toast.error(errorDetail(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void fetchAll(); }, [fetchAll]);

  const openCreate = () => {
    setEditorMode("create");
    setEditing(null);
    setEditorOpen(true);
  };

  const openEdit = (item: MainConfig) => {
    setEditorMode("edit");
    setEditing(item);
    setEditorOpen(true);
  };

  const openDuplicate = (item: MainConfig) => {
    setEditorMode("duplicate");
    setEditing(item);
    setEditorOpen(true);
  };

  const closeEditor = () => {
    setEditorOpen(false);
    setEditing(null);
  };

  const handlePreview = async (item: MainConfig) => {
    try {
      const res = await api.post<PreviewResponse>(`/admin/main-configs/${item.id}/preview`);
      setPreviewYaml(res.data.yaml);
      setPreviewDiagnostics(res.data.diagnostics);
      setPreviewOpen(true);
    } catch (err) {
      toast.error(errorDetail(err));
    }
  };

  const handleCopyArtifactLink = async (item: MainConfig) => {
    const link = `${window.location.origin}/api/public/configs/${item.id}/artifact`;
    await navigator.clipboard.writeText(link);
    toast.success("Link copied to clipboard");
  };

  const handleDelete = async (item: MainConfig) => {
    try {
      await api.delete(`/admin/main-configs/${item.id}`);
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
      await api.put("/admin/main-configs/reorder", {
        items: reordered.map((item, i) => ({ id: item.id, position: i + 1 })),
      });
    } catch (err) {
      toast.error(errorDetail(err));
      await fetchAll();
    }
  };

  const renderCard = (item: MainConfig, dragHandle: ReactNode) => (
    <Card key={item.id} className="flex flex-col">
      <CardHeader className="pb-2">
        <div className="flex items-center gap-2">
          {dragHandle}
          <CardTitle className="text-base flex-1 truncate">{item.name}</CardTitle>
        </div>
        <div className="flex flex-wrap gap-1 mt-1">
          <Badge variant="outline" className="border-blue-400 text-blue-600">
            {item.final_target_type === "group" ? item.final_target_group_name : item.final_target_type}
          </Badge>
          <Badge variant={item.enabled ? "default" : "secondary"} className={item.enabled ? "bg-green-600" : ""}>
            {item.enabled ? "on" : "off"}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="flex-1">
        <div className="flex flex-wrap gap-1 pt-2">
          <Button variant="outline" size="sm" title="Edit" onClick={() => openEdit(item)}>
            <Pencil className="h-3 w-3" />
          </Button>
          <Button variant="outline" size="sm" title="Duplicate" onClick={() => openDuplicate(item)}>
            <Copy className="h-3 w-3" />
          </Button>
          <Button variant="outline" size="sm" title="Preview" onClick={() => void handlePreview(item)}>
            <Eye className="h-3 w-3" />
          </Button>
          <Button variant="outline" size="sm" title="Copy URL" onClick={() => void handleCopyArtifactLink(item)}>
            <Link className="h-3 w-3" />
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
          <Plus className="h-4 w-4 mr-1" /> New Config
        </Button>
      </div>

      <CardGrid
        items={items}
        loading={loading}
        rowKey={(item) => item.id}
        renderCard={renderCard}
        onReorder={handleReorder}
      />

      <MainConfigEditorDrawer
        open={editorOpen}
        config={editing}
        mode={editorMode}
        configs={items}
        subscriptions={subscriptions}
        routeTemplates={routeTemplates}
        onClose={closeEditor}
        onSaved={fetchAll}
      />

      {/* Preview Dialog */}
      <Dialog open={previewOpen} onOpenChange={setPreviewOpen}>
        <DialogContent className="max-w-3xl lg:max-w-5xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Config Preview</DialogTitle>
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
    </div>
  );
}
