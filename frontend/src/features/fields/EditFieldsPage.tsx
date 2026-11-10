import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router";

import { ResponsiveSheet } from "@/components/ResponsiveSheet";

import { EditFieldsForm } from "./EditFieldsForm";
import { useFieldsScreen } from "./useFieldsScreen";

/** Screen 6d, over the fields: add or remove fields (FR-090, BR-132). */
export function EditFieldsPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const screen = useFieldsScreen();

  return (
    <ResponsiveSheet
      title={t("fields.edit.heading")}
      description={t("fields.edit.description")}
    >
      {screen.model && (
        <EditFieldsForm
          leagueId={screen.leagueId}
          model={screen.model}
          onDone={() => {
            void navigate("..");
          }}
        />
      )}
    </ResponsiveSheet>
  );
}
