import type { ComponentProps } from "react";

// The icons the finals screens need (24 px, 2 px stroke), drawn here as our
// own SVG components (docs/style/frontend-style.md §5.3). Hidden from
// assistive technology: the control around them carries the name.

function Icon(props: ComponentProps<"svg">) {
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
      {...props}
    />
  );
}

export function ChevronDownIcon(props: ComponentProps<"svg">) {
  return (
    <Icon {...props}>
      <path d="m6 9 6 6 6-6" />
    </Icon>
  );
}
