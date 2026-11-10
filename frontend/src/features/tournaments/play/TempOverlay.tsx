import type { ReactNode } from "react";
import { useNavigate } from "react-router";

import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { useLayout } from "@/hooks/useLayout";

// TODO(foundation-sheet): components/ResponsiveSheet replaces this stand-in
// with the rebase; the props are the same.
export function TempOverlay({
  title,
  description,
  closeTo,
  children,
}: {
  title: ReactNode;
  description?: ReactNode;
  closeTo: string;
  children: ReactNode;
}) {
  const navigate = useNavigate();
  const layout = useLayout();
  return (
    <Sheet
      open
      onOpenChange={(open) => {
        if (!open) {
          void navigate(closeTo);
        }
      }}
    >
      <SheetContent
        side={layout === "phone" ? "bottom" : "right"}
        className="w-full overflow-y-auto sm:max-w-md"
      >
        <SheetHeader>
          <SheetTitle>{title}</SheetTitle>
          {description !== undefined && (
            <SheetDescription className="text-body-sm">
              {description}
            </SheetDescription>
          )}
        </SheetHeader>
        {children}
      </SheetContent>
    </Sheet>
  );
}
