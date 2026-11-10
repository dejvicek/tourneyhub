import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router";

import { DocumentTitle } from "@/components/DocumentTitle";
import { TempOverlay } from "@/features/tournaments/play/TempOverlay";

import { EditFieldsForm } from "./EditFieldsForm";
import { useFieldsScreen } from "./useFieldsScreen";

/** Screen 6d: add or remove fields (FR-090, BR-132). */
export function EditFieldsPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const screen = useFieldsScreen();

  return (
    <>
      <DocumentTitle screen={t("fields.edit.title")} />
      <TempOverlay
        title={t("fields.edit.heading")}
        description={t("fields.edit.description")}
        closeTo={screen.fieldsPath}
      >
        {screen.model && (
          <EditFieldsForm
            leagueId={screen.leagueId}
            model={screen.model}
            onDone={() => {
              void navigate(screen.fieldsPath);
            }}
          />
        )}
      </TempOverlay>
    </>
  );
}
