import { cva, type VariantProps } from "class-variance-authority";
import { Slot } from "radix-ui";
import * as React from "react";

import { cn } from "@/lib/utils";

// Project-wide changes (docs/style/frontend-style.md §5.2, §6): a solid focus ring
// with a background-coloured offset, 3:1 against every surface and the
// button itself (WCAG 1.4.11, technique C40); destructive uses its token
// pair. Sizes and variants follow the Figma Button (components.md): no size
// is below 44 px, the phone's touch target.
//
// size default  Compact, 44 px, radius 8, Button/Small
// size lg       Primary, 56 px, radius 10, Button/Large
// size icon     44 × 44, round, like the Back button
// feature       the white button on the green playfield, 52 px, radius 10
// text          a plain label without fill, e.g. "Back" or "Cancel"

const buttonVariants = cva(
  "inline-flex shrink-0 items-center justify-center gap-2 whitespace-nowrap outline-hidden transition-all focus-visible:ring-[3px] focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background disabled:pointer-events-none disabled:opacity-50 aria-invalid:border-destructive aria-invalid:ring-destructive/20 dark:aria-invalid:ring-destructive/40 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-5",
  {
    variants: {
      variant: {
        default: "bg-primary text-primary-foreground hover:bg-primary/90",
        destructive:
          "bg-destructive text-destructive-foreground hover:bg-destructive/90",
        outline:
          "border bg-background shadow-xs hover:bg-accent hover:text-accent-foreground dark:border-input dark:bg-input/30 dark:hover:bg-input/50",
        secondary:
          "bg-secondary text-secondary-foreground hover:bg-secondary/80",
        ghost:
          "hover:bg-accent hover:text-accent-foreground dark:hover:bg-accent/50",
        feature: "bg-feature text-feature-foreground hover:bg-feature/90",
        text: "text-foreground underline-offset-4 hover:underline",
      },
      size: {
        default: "h-11 rounded-md px-4 text-button-sm has-[>svg]:px-3",
        lg: "h-14 rounded-lg px-6 text-button-lg has-[>svg]:px-5",
        icon: "size-11 rounded-full",
      },
    },
    compoundVariants: [
      {
        variant: "feature",
        size: ["default", "lg"],
        class: "h-13 rounded-lg px-6 text-button-lg",
      },
      {
        variant: "text",
        size: ["default", "lg"],
        class: "px-2 text-body-md",
      },
    ],
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  },
);

function Button({
  className,
  variant = "default",
  size = "default",
  asChild = false,
  ...props
}: React.ComponentProps<"button"> &
  VariantProps<typeof buttonVariants> & {
    asChild?: boolean;
  }) {
  const Comp = asChild ? Slot.Root : "button";

  return (
    <Comp
      data-slot="button"
      data-variant={variant}
      data-size={size}
      className={cn(buttonVariants({ variant, size, className }))}
      {...props}
    />
  );
}

export { Button, buttonVariants };
