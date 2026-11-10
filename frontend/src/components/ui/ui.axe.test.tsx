import { render, screen } from "@testing-library/react";
import axe from "axe-core";
import type { AriaRole as ARIARole, ReactElement } from "react";
import { beforeAll, beforeEach, describe, expect, it } from "vitest";

import { i18n } from "@/i18n";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "./alert-dialog";
import { Badge } from "./badge";
import { Button } from "./button";
import { Card, CardContent, CardHeader, CardTitle } from "./card";
import { Checkbox } from "./checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "./dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "./dropdown-menu";
import { Input } from "./input";
import { Label } from "./label";
import { RadioGroup, RadioGroupItem } from "./radio-group";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "./select";
import { Separator } from "./separator";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "./sheet";
import { Skeleton } from "./skeleton";
import { Switch } from "./switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "./tabs";
import { Textarea } from "./textarea";
import { ToggleGroup, ToggleGroupItem } from "./toggle-group";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "./tooltip";

function Page() {
  return (
    <main>
      <h1>Components</h1>
      <Card>
        <CardHeader>
          <CardTitle>
            <h2>Setup</h2>
          </CardTitle>
        </CardHeader>
        <CardContent className="grid gap-3">
          <Label htmlFor="name">Name</Label>
          <Input id="name" defaultValue="Thursday Foosball" />
          <Label htmlFor="notes">Notes</Label>
          <Textarea id="notes" />
          <Select>
            <SelectTrigger aria-label="Format">
              <span>DYP</span>
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="dyp">DYP</SelectItem>
            </SelectContent>
          </Select>
          <div className="flex items-center gap-3">
            <Checkbox id="here" aria-label="Here tonight" />
            <Switch aria-label="Late players" />
          </div>
          <RadioGroup aria-label="Type" defaultValue="a">
            <RadioGroupItem value="a" aria-label="Singles" />
            <RadioGroupItem value="b" aria-label="Doubles" />
          </RadioGroup>
          <ToggleGroup type="single" aria-label="Seeding">
            <ToggleGroupItem value="league">League</ToggleGroupItem>
            <ToggleGroupItem value="random">Random</ToggleGroupItem>
          </ToggleGroup>
          <Tabs defaultValue="rr">
            <TabsList aria-label="Phase">
              <TabsTrigger value="rr">Round robin</TabsTrigger>
              <TabsTrigger value="ko">Knockout</TabsTrigger>
            </TabsList>
            <TabsContent value="rr">Round robin matches</TabsContent>
          </Tabs>
          <Separator />
          <Badge>Field 1</Badge>
          <Skeleton className="h-4 w-24" />
          <Button>Save</Button>
        </CardContent>
      </Card>
    </main>
  );
}

// jsdom computes no layout and applies no stylesheet, so colour-contrast
// cannot run here, in either colour scheme: the ratios of the tokens are
// asserted from a script (guide §5.2), and axe checks the structure, the
// same in both themes: names, roles, ARIA, labels. Playwright runs axe in
// both schemes in a real browser (ADR-013).
async function violations(root: Element = document.body) {
  const results = await axe.run(root, {
    runOnly: [
      "wcag2a",
      "wcag2aa",
      "wcag21a",
      "wcag21aa",
      "wcag22aa",
      "best-practice",
    ],
    rules: { "color-contrast": { enabled: false }, region: { enabled: false } },
  });
  return results.violations.map((v) => `${v.id}: ${v.help}`);
}

// jsdom lacks the pointer-capture and scrolling methods Radix calls.
beforeAll(() => {
  Element.prototype.hasPointerCapture = () => false;
  Element.prototype.setPointerCapture = () => undefined;
  Element.prototype.releasePointerCapture = () => undefined;
  Element.prototype.scrollIntoView = () => undefined;
});

beforeEach(async () => {
  await i18n.changeLanguage("en");
});

describe("UI components", () => {
  it("have no axe violations on a page", async () => {
    render(<Page />);

    expect(await violations()).toEqual([]);
  });
});

// Each overlay open, as it renders into its portal at the end of <body>.
const OPEN: [string, ARIARole, () => ReactElement][] = [
  [
    "Dialog",
    "dialog",
    () => (
      <Dialog open>
        <DialogTrigger asChild>
          <Button>Delete round 5</Button>
        </DialogTrigger>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete round 5</DialogTitle>
            <DialogDescription>Its results are lost.</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button>Delete</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    ),
  ],
  [
    "Sheet",
    "dialog",
    () => (
      <Sheet open>
        <SheetTrigger asChild>
          <Button>Manage fields</Button>
        </SheetTrigger>
        <SheetContent side="bottom">
          <SheetHeader>
            <SheetTitle>Fields</SheetTitle>
            <SheetDescription>Add or remove a field.</SheetDescription>
          </SheetHeader>
          <SheetFooter>
            <Button size="lg">Done</Button>
          </SheetFooter>
        </SheetContent>
      </Sheet>
    ),
  ],
  [
    "AlertDialog",
    "alertdialog",
    () => (
      <AlertDialog open>
        <AlertDialogTrigger asChild>
          <Button variant="destructive">Remove</Button>
        </AlertDialogTrigger>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Remove Field 2?</AlertDialogTitle>
            <AlertDialogDescription>
              Its match goes back to the waiting list.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction>Remove</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    ),
  ],
  [
    "Select",
    "listbox",
    () => (
      <Select open defaultValue="dyp">
        <SelectTrigger aria-label="Type">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="singles">Singles</SelectItem>
          <SelectItem value="dyp">DYP</SelectItem>
        </SelectContent>
      </Select>
    ),
  ],
  [
    "DropdownMenu",
    "menu",
    () => (
      <DropdownMenu open>
        <DropdownMenuTrigger asChild>
          <Button>Round 5</Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent>
          <DropdownMenuLabel>Round 5</DropdownMenuLabel>
          <DropdownMenuItem>Add round 6</DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem variant="destructive">
            Delete round 5
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    ),
  ],
  [
    "Tooltip",
    "tooltip",
    () => (
      <TooltipProvider>
        <Tooltip open>
          <TooltipTrigger asChild>
            <Button>BH1</Button>
          </TooltipTrigger>
          <TooltipContent>Buchholz: the opponents' points</TooltipContent>
        </Tooltip>
      </TooltipProvider>
    ),
  ],
];

describe.each(OPEN)("%s, open", (_, role, Open) => {
  it("has no axe violations in its portal", async () => {
    render(
      <main>
        <h1>Overlay</h1>
        <Open />
      </main>,
    );
    const portal = await screen.findByRole(role);

    expect(portal).toBeVisible();
    expect(await violations()).toEqual([]);
  });
});
