import { render } from "@testing-library/react";
import axe from "axe-core";
import { describe, expect, it, vi } from "vitest";

import { i18n } from "@/i18n";
import { stubViewport } from "@/test/media";

import { Badge } from "./badge";
import { Button } from "./button";
import { Card, CardContent, CardHeader, CardTitle } from "./card";
import { Checkbox } from "./checkbox";
import { Input } from "./input";
import { Label } from "./label";
import { RadioGroup, RadioGroupItem } from "./radio-group";
import { Select, SelectContent, SelectItem, SelectTrigger } from "./select";
import { Separator } from "./separator";
import { Skeleton } from "./skeleton";
import { Switch } from "./switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "./tabs";
import { Textarea } from "./textarea";
import { ToggleGroup, ToggleGroupItem } from "./toggle-group";

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

// jsdom computes no layout or colours, so colour-contrast cannot run here:
// the ratios of the tokens are asserted from a script (guide §5.2) and axe
// runs on the structure: names, roles, ARIA, labels.
async function violations() {
  const { container } = render(<Page />);
  const results = await axe.run(container, {
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

describe.each(["light", "dark"] as const)("UI components in %s", (scheme) => {
  it("have no axe violations", async () => {
    await i18n.changeLanguage("en");
    stubViewport(390);
    const query = (q: string) => ({
      matches: q.includes("prefers-color-scheme: dark") === (scheme === "dark"),
      media: q,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
    });
    vi.stubGlobal("matchMedia", query);
    document.documentElement.style.colorScheme = scheme;

    expect(await violations()).toEqual([]);
  });
});
