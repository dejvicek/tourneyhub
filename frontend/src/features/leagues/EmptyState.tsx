import type { ReactNode } from "react";

interface EmptyStateProps {
  title: string;
  body?: string;
  /** An action, such as the form that adds the first item. */
  children?: ReactNode;
}

/** A list with nothing in it yet: a dashed card, as a free field in the design. */
export function EmptyState({ title, body, children }: EmptyStateProps) {
  return (
    <div className="space-y-3 rounded-lg border-2 border-dashed border-border px-4 py-6 text-center">
      <p className="font-display text-display-section">{title}</p>
      {body !== undefined && (
        <p className="text-body-md text-muted-foreground">{body}</p>
      )}
      {children}
    </div>
  );
}
