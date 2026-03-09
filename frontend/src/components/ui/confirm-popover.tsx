import { useState } from "react"

import { Button } from "@/components/ui/button"
import {
  Popover,
  PopoverContent,
  PopoverDescription,
  PopoverTrigger,
} from "@/components/ui/popover"

interface ConfirmPopoverProps {
  description: string
  onConfirm: () => void
  confirmText?: string
  cancelText?: string
  side?: "top" | "bottom" | "left" | "right"
  align?: "center" | "start" | "end"
  children: React.ReactElement
}

export function ConfirmPopover({
  description,
  onConfirm,
  confirmText = "Delete",
  cancelText = "Cancel",
  side,
  align,
  children,
}: ConfirmPopoverProps) {
  const [open, setOpen] = useState(false)

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger render={children} />
      <PopoverContent side={side} align={align} className="w-auto max-w-64">
        <PopoverDescription>{description}</PopoverDescription>
        <div className="flex justify-end gap-2">
          <Button variant="outline" size="sm" onClick={() => setOpen(false)}>
            {cancelText}
          </Button>
          <Button
            variant="destructive"
            size="sm"
            onClick={() => {
              setOpen(false)
              onConfirm()
            }}
          >
            {confirmText}
          </Button>
        </div>
      </PopoverContent>
    </Popover>
  )
}
