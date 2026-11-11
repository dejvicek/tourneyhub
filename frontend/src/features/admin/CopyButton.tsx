import { useState } from "react";

import { Button } from "@/components/ui/button";

interface CopyButtonProps {
  text: string;
  label: string;
  copied: string;
  failed: string;
}

/** Copies `text` to the clipboard and announces the outcome. */
export function CopyButton({ text, label, copied, failed }: CopyButtonProps) {
  const [status, setStatus] = useState<"copied" | "failed" | null>(null);

  return (
    <div className="space-y-1">
      <Button
        type="button"
        variant="outline"
        className="w-full sm:w-auto"
        onClick={() => {
          navigator.clipboard.writeText(text).then(
            () => {
              setStatus("copied");
            },
            () => {
              setStatus("failed");
            },
          );
        }}
      >
        {label}
      </Button>
      <p role="status" className="text-caption text-muted-foreground">
        {status === "copied" && copied}
        {status === "failed" && failed}
      </p>
    </div>
  );
}
