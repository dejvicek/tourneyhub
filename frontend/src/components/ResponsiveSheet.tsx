import type { ReactNode } from "react";
import { useNavigate } from "react-router";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { useLayout } from "@/hooks/useLayout";

export interface ResponsiveSheetProps {
  title: string;
  /** One line under the title; the dialog's accessible description. */
  description?: string;
  children?: ReactNode;
  /** The actions at the bottom, such as "Save result" and "Cancel". */
  footer?: ReactNode;
}

/**
 * An overlay over its parent screen (Figma 6c, 6d, 7 and 7b): a bottom sheet
 * on a phone, a centred dialog from `md` and a side panel on the right from
 * `lg`, which leaves the screen behind it usable. It is the page of a nested
 * route and always open; closing it goes to the parent route.
 */
export function ResponsiveSheet({
  title,
  description,
  children,
  footer,
}: ResponsiveSheetProps) {
  const layout = useLayout();
  const navigate = useNavigate();
  const onOpenChange = (open: boolean) => {
    if (!open) {
      void navigate("..");
    }
  };
  // Radix warns about a dialog without a description unless it is told
  // there is none.
  const describedBy =
    description === undefined ? { "aria-describedby": undefined } : {};

  if (layout === "tablet") {
    return (
      <Dialog open onOpenChange={onOpenChange}>
        <DialogContent {...describedBy}>
          <DialogHeader>
            <DialogTitle>{title}</DialogTitle>
            {description !== undefined && (
              <DialogDescription>{description}</DialogDescription>
            )}
          </DialogHeader>
          {children}
          {footer !== undefined && <DialogFooter>{footer}</DialogFooter>}
        </DialogContent>
      </Dialog>
    );
  }

  const desktop = layout === "desktop";
  return (
    <Sheet open modal={!desktop} onOpenChange={onOpenChange}>
      <SheetContent
        side={desktop ? "right" : "bottom"}
        {...describedBy}
        // The side panel stays open while the organizer works beside it;
        // only its close button or Escape closes it.
        onInteractOutside={
          desktop
            ? (event) => {
                event.preventDefault();
              }
            : undefined
        }
        className={desktop ? "overflow-y-auto sm:max-w-md" : undefined}
      >
        <SheetHeader>
          <SheetTitle>{title}</SheetTitle>
          {description !== undefined && (
            <SheetDescription>{description}</SheetDescription>
          )}
        </SheetHeader>
        {children}
        {footer !== undefined && <SheetFooter>{footer}</SheetFooter>}
      </SheetContent>
    </Sheet>
  );
}
