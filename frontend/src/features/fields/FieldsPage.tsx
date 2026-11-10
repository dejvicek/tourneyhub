import { useTranslation } from "react-i18next";
import { Outlet } from "react-router";

import { PlaceholderPage } from "@/components/PlaceholderPage";

// Placeholder (FR-090–FR-092). Moving a match (6c), editing the fields
// (6d) and entering a result open over it (<Outlet />).
export function FieldsPage() {
  const { t } = useTranslation();
  return (
    <PlaceholderPage screen="6b" title={t("fields.now.title")}>
      <Outlet />
    </PlaceholderPage>
  );
}
