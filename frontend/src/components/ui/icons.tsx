import * as React from "react";

// The few glyphs the copied components draw. lucide-react is not installed
// until a screen needs a real icon (docs/frontend-style.md §5.3); these are
// 24 px, 2 px stroke like the design's icon set, and hidden from assistive
// technology because the control around them carries the name.

function Icon({ className, ...props }: React.ComponentProps<"svg">) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className={className}
      {...props}
    />
  );
}

function CheckIcon(props: React.ComponentProps<"svg">) {
  return (
    <Icon {...props}>
      <path d="M20 6 9 17l-5-5" />
    </Icon>
  );
}

function CloseIcon(props: React.ComponentProps<"svg">) {
  return (
    <Icon {...props}>
      <path d="M18 6 6 18M6 6l12 12" />
    </Icon>
  );
}

function ChevronDownIcon(props: React.ComponentProps<"svg">) {
  return (
    <Icon {...props}>
      <path d="m6 9 6 6 6-6" />
    </Icon>
  );
}

function ChevronUpIcon(props: React.ComponentProps<"svg">) {
  return (
    <Icon {...props}>
      <path d="m18 15-6-6-6 6" />
    </Icon>
  );
}

export { CheckIcon, ChevronDownIcon, ChevronUpIcon, CloseIcon };
