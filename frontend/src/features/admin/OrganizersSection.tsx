import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { PageFallback } from "@/components/PageFallback";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { SettingsSection } from "@/features/leagues/SettingsSection";

import { adminQueries } from "./api";
import { ResetPasswordDialog } from "./ResetPasswordDialog";

/**
 * The accounts of this instance (FR-006, ADR-007) with "Reset password" for
 * each but the admin's own, which would end the admin's own login.
 */
export function OrganizersSection({ myId }: { myId: string | undefined }) {
  const { t } = useTranslation();
  const organizers = useQuery(adminQueries.organizers());

  return (
    <SettingsSection
      id="organizers"
      title={t("admin.organizers.heading")}
      description={t("admin.organizers.lead")}
    >
      {organizers.isPending ? (
        <PageFallback />
      ) : organizers.isError ? (
        <div role="alert" className="space-y-3">
          <p className="text-body-md">{t("admin.loadFailed")}</p>
          <Button
            type="button"
            variant="outline"
            onClick={() => {
              void organizers.refetch();
            }}
          >
            {t("admin.retry")}
          </Button>
        </div>
      ) : organizers.data.length === 0 ? (
        <p className="text-body-md text-muted-foreground">
          {t("admin.organizers.empty")}
        </p>
      ) : (
        <ul className="divide-y divide-border-surface">
          {organizers.data.map((organizer) => (
            <li
              key={organizer.id}
              className="flex flex-col gap-3 py-3 first:pt-0 last:pb-0 sm:flex-row sm:items-center sm:justify-between"
            >
              <div className="min-w-0 space-y-1">
                <p className="font-display text-display-name break-words">
                  {organizer.display_name}
                </p>
                <p className="text-body-sm break-words text-muted-foreground">
                  {organizer.email}
                </p>
                <div className="flex flex-wrap gap-1.5">
                  {organizer.id === myId && (
                    <Badge variant="outline">{t("admin.organizers.you")}</Badge>
                  )}
                  {organizer.is_admin && (
                    <Badge variant="secondary">
                      {t("admin.organizers.admin")}
                    </Badge>
                  )}
                  {organizer.must_change_password && (
                    <Badge variant="warning">
                      {t("admin.organizers.mustChange")}
                    </Badge>
                  )}
                </div>
              </div>
              {organizer.id !== myId && (
                <ResetPasswordDialog
                  userId={organizer.id}
                  name={organizer.display_name}
                />
              )}
            </li>
          ))}
        </ul>
      )}
    </SettingsSection>
  );
}
