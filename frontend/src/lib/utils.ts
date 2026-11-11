// The one `cn` of the app (docs/style/frontend-style.md §5.3), the path that
// components.json names as shadcn's `utils` alias. It is the `cn` package
// configured with the theme's text styles (src/index.css): unconfigured, it
// would take `text-caption` for a colour and drop `text-muted-foreground`
// beside it.
import { createCn } from "cn/config";

/** The Figma text styles, `--text-*` in the @theme block of index.css. */
const TEXT_STYLES = [
  "display-hero",
  "display-title",
  "display-screen",
  "display-name",
  "display-section",
  "score-xl",
  "score-l",
  "score-m",
  "score-s",
  "body-lg",
  "body-md",
  "body-sm",
  "button-lg",
  "button-sm",
  "caption",
  "micro",
];

export const cn = createCn({
  extend: { classGroups: { "font-size": [{ text: TEXT_STYLES }] } },
});
