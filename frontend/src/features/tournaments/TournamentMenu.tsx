import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { MoreIcon } from "@/components/ui/icons";
import { AccountMenuItems } from "@/features/auth/AccountMenu";
import { isLanguage, LANGUAGES, rememberLanguage } from "@/i18n/language";

/**
 * Inside a tournament the phone has no league header, which carries the
 * language switch and the account menu everywhere else. This overflow menu
 * in the tournament's header keeps both within reach.
 */
export function TournamentMenu() {
  const { t, i18n } = useTranslation();
  const current = isLanguage(i18n.resolvedLanguage)
    ? i18n.resolvedLanguage
    : undefined;

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          aria-label={t("tournaments.header.menu")}
        >
          <MoreIcon />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="min-w-56">
        <DropdownMenuLabel className="text-body-sm font-normal text-muted-foreground">
          {t("language.switchLabel")}
        </DropdownMenuLabel>
        <DropdownMenuRadioGroup
          value={current}
          onValueChange={(language) => {
            if (isLanguage(language)) {
              rememberLanguage(language);
              void i18n.changeLanguage(language);
            }
          }}
        >
          {LANGUAGES.map((language) => (
            <DropdownMenuRadioItem
              key={language}
              value={language}
              lang={language}
              className="text-body-md"
            >
              {t(`language.${language}.name`)}
            </DropdownMenuRadioItem>
          ))}
        </DropdownMenuRadioGroup>
        <DropdownMenuSeparator />
        <AccountMenuItems />
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
