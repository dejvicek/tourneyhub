import "i18next";

import type { Messages } from "./locales/en";

declare module "i18next" {
  interface CustomTypeOptions {
    defaultNS: "translation";
    resources: {
      translation: Messages;
    };
  }
}
