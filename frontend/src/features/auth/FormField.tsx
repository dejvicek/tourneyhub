import { type ComponentProps, type ReactNode, useId } from "react";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

interface FormFieldProps extends Omit<ComponentProps<typeof Input>, "id"> {
  label: string;
  /** Shown under the field, before and after validation. */
  hint?: ReactNode;
  /** The server's message for this field (ADR-008); none before validation. */
  error?: string;
}

/**
 * A labelled text field with its hint and error (docs/frontend-style.md §6):
 * after a failed validation the input gets aria-invalid and is described by
 * the message, which is text, never colour alone.
 */
export function FormField({
  label,
  hint,
  error,
  className,
  ...input
}: FormFieldProps) {
  const id = useId();
  const hintId = `${id}-hint`;
  const errorId = `${id}-error`;
  const describedBy = [
    hint === undefined ? undefined : hintId,
    error === undefined ? undefined : errorId,
  ]
    .filter((value) => value !== undefined)
    .join(" ");

  return (
    <div className={cn("space-y-1.5", className)}>
      <Label htmlFor={id} className="text-body-sm">
        {label}
      </Label>
      <Input
        id={id}
        aria-invalid={error === undefined ? undefined : true}
        aria-describedby={describedBy === "" ? undefined : describedBy}
        className="text-base"
        {...input}
      />
      {hint !== undefined && (
        <p id={hintId} className="text-body-sm text-muted-foreground">
          {hint}
        </p>
      )}
      {error !== undefined && (
        <p id={errorId} className="text-body-sm font-bold text-destructive">
          {error}
        </p>
      )}
    </div>
  );
}
