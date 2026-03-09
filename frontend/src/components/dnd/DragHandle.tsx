import { forwardRef } from "react";
import { GripVertical } from "lucide-react";
import type { SyntheticListenerMap } from "@dnd-kit/core/dist/hooks/utilities";

interface DragHandleProps {
  listeners?: SyntheticListenerMap;
}

const DragHandle = forwardRef<HTMLSpanElement, DragHandleProps>(
  ({ listeners }, ref) => (
    <span
      ref={ref}
      {...listeners}
      style={{ cursor: "grab", touchAction: "none", display: "inline-flex", alignItems: "center" }}
    >
      <GripVertical className="h-4 w-4 text-muted-foreground" />
    </span>
  ),
);

DragHandle.displayName = "DragHandle";

export default DragHandle;
