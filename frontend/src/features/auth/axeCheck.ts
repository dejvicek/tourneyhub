// Test helper: axe on the rendered page, as src/components/ui/ui.axe.test.tsx
// runs it. jsdom computes no colours, so colour contrast is checked from the
// tokens' recorded ratios (docs/style/frontend-style.md §5.2), not here.
import axe from "axe-core";

export async function axeViolations(): Promise<string[]> {
  const results = await axe.run(document.body, {
    runOnly: [
      "wcag2a",
      "wcag2aa",
      "wcag21a",
      "wcag21aa",
      "wcag22aa",
      "best-practice",
    ],
    rules: { "color-contrast": { enabled: false } },
  });
  return results.violations.map(
    (v) => `${v.id}: ${v.help} (${v.nodes.map((n) => n.html).join(" | ")})`,
  );
}
