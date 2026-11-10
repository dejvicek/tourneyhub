import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeAll, describe, expect, it } from "vitest";

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "./select";

// jsdom lacks the pointer-capture and scrolling methods Radix calls.
beforeAll(() => {
  Element.prototype.hasPointerCapture = () => false;
  Element.prototype.setPointerCapture = () => undefined;
  Element.prototype.releasePointerCapture = () => undefined;
  Element.prototype.scrollIntoView = () => undefined;
});

describe("Select", () => {
  it("opens with the keyboard, moves with the arrows and picks with Enter", async () => {
    const user = userEvent.setup();
    render(
      <Select>
        <SelectTrigger aria-label="Format">
          <SelectValue placeholder="Choose" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="dyp">DYP</SelectItem>
          <SelectItem value="doubles">Doubles</SelectItem>
          <SelectItem value="singles">Singles</SelectItem>
        </SelectContent>
      </Select>,
    );

    await user.tab();
    expect(screen.getByRole("combobox", { name: "Format" })).toHaveFocus();

    await user.keyboard("{Enter}");
    expect(await screen.findByRole("listbox")).toBeInTheDocument();

    await user.keyboard("{ArrowDown}");
    await user.keyboard("{Enter}");

    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Format" })).toHaveTextContent(
      "Doubles",
    );
  });
});
