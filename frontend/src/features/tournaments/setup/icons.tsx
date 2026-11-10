import type { ComponentProps } from "react";

// The design's icon set (24 px, 2 px stroke) for the setup screens;
// lucide-react is not installed (docs/frontend-style.md §5.3). The control
// around an icon carries the name, so the icons are hidden from assistive
// technology.

function Icon({ className, ...props }: ComponentProps<"svg">) {
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

export function SearchIcon(props: ComponentProps<"svg">) {
  return (
    <Icon {...props}>
      <circle cx="11" cy="11" r="7" />
      <path d="m20 20-3.5-3.5" />
    </Icon>
  );
}

export function ShuffleIcon(props: ComponentProps<"svg">) {
  return (
    <Icon {...props}>
      <path d="M16 3h5v5M4 20 21 3M21 16v5h-5M15 15l6 6M4 4l5 5" />
    </Icon>
  );
}

export function PersonPlusIcon(props: ComponentProps<"svg">) {
  return (
    <Icon {...props}>
      <circle cx="9" cy="8" r="4" />
      <path d="M2 21a7 7 0 0 1 14 0M19 8v6M16 11h6" />
    </Icon>
  );
}

export function InfoIcon(props: ComponentProps<"svg">) {
  return (
    <Icon {...props}>
      <circle cx="12" cy="12" r="10" />
      <path d="M12 16v-4M12 8h.01" />
    </Icon>
  );
}

export function WarningIcon(props: ComponentProps<"svg">) {
  return (
    <Icon {...props}>
      <path d="m21.7 18-8-14a2 2 0 0 0-3.4 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.7-3ZM12 9v4M12 17h.01" />
    </Icon>
  );
}

export function ArrowUpIcon(props: ComponentProps<"svg">) {
  return (
    <Icon {...props}>
      <path d="m5 12 7-7 7 7M12 19V5" />
    </Icon>
  );
}

export function ArrowDownIcon(props: ComponentProps<"svg">) {
  return (
    <Icon {...props}>
      <path d="m19 12-7 7-7-7M12 5v14" />
    </Icon>
  );
}

export function MoreIcon(props: ComponentProps<"svg">) {
  return (
    <Icon {...props}>
      <circle cx="12" cy="5" r="1" />
      <circle cx="12" cy="12" r="1" />
      <circle cx="12" cy="19" r="1" />
    </Icon>
  );
}

export function PlusIcon(props: ComponentProps<"svg">) {
  return (
    <Icon {...props}>
      <path d="M5 12h14M12 5v14" />
    </Icon>
  );
}

export function MinusIcon(props: ComponentProps<"svg">) {
  return (
    <Icon {...props}>
      <path d="M5 12h14" />
    </Icon>
  );
}
