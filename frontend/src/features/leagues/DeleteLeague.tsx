import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router";

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
} from "@/components/ui/alert-dialog";
import { Button, buttonVariants } from "@/components/ui/button";
import { paths } from "@/lib/paths";

import { leagueMutations } from "./api";
import { SettingsSection } from "./SettingsSection";

/** FR-013: deletes the league after a confirmation that names it. */
export function DeleteLeague({
  leagueId,
  name,
}: {
  leagueId: string;
  name: string;
}) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const remove = useMutation(leagueMutations.delete(queryClient, leagueId));

  return (
    <SettingsSection
      id="delete-league"
      title={t("leagues.settings.danger.heading")}
      description={t("leagues.settings.danger.body")}
    >
      <AlertDialog>
        <AlertDialogTrigger asChild>
          <Button
            type="button"
            variant="destructive"
            className="w-full sm:w-auto"
            disabled={remove.isPending}
          >
            {remove.isPending
              ? t("leagues.settings.danger.deleting")
              : t("leagues.settings.danger.delete")}
          </Button>
        </AlertDialogTrigger>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {t("leagues.settings.danger.confirmTitle", { name })}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {t("leagues.settings.danger.confirmBody", { name })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>
              {t("leagues.settings.danger.cancel")}
            </AlertDialogCancel>
            <AlertDialogAction
              className={buttonVariants({ variant: "destructive" })}
              onClick={() => {
                // A 404 means it is gone already (ADR-008): same place.
                remove.mutate(undefined, {
                  onSettled: () => {
                    void navigate(paths.myLeagues, { replace: true });
                  },
                });
              }}
            >
              {t("leagues.settings.danger.confirm")}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </SettingsSection>
  );
}
