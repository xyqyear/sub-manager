import { forwardRef } from "react";
import { HolderOutlined } from "@ant-design/icons";
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
      <HolderOutlined />
    </span>
  ),
);

DragHandle.displayName = "DragHandle";

export default DragHandle;
