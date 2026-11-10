import { describe, expect, it } from "vitest";

import { buttonVariants } from "@/components/ui/button";

import { cn } from "./utils";

describe("cn", () => {
  it("keeps a theme text style beside a text colour", () => {
    expect(cn("text-caption text-muted-foreground")).toBe(
      "text-caption text-muted-foreground",
    );
    expect(cn("bg-primary text-primary-foreground", "text-button-sm")).toBe(
      "bg-primary text-primary-foreground text-button-sm",
    );
  });

  it("keeps only the last of two text styles", () => {
    expect(cn("text-caption", "text-body-md")).toBe("text-body-md");
  });

  it("gives Button, as it merges its classes, both text style and colour", () => {
    expect(cn(buttonVariants()).split(" ")).toEqual(
      expect.arrayContaining(["text-primary-foreground", "text-button-sm"]),
    );
    expect(cn(buttonVariants({ variant: "text" })).split(" ")).toEqual(
      expect.arrayContaining(["text-foreground", "text-body-md"]),
    );
    expect(cn(buttonVariants({ variant: "text" }))).not.toContain(
      "text-button-sm",
    );
  });
});
