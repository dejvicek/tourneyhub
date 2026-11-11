import { useTranslation } from "react-i18next";

import { Label } from "@/components/ui/label";

/** One switch for every password field of a form, for typing on a phone. */
export function ShowPasswords({
  checked,
  onChange,
}: {
  checked: boolean;
  onChange: (checked: boolean) => void;
}) {
  const { t } = useTranslation();
  return (
    <div className="flex min-h-11 items-center gap-3">
      {/* Native: Radix's checkbox needs ResizeObserver inside a form. */}
      <input
        id="show-passwords"
        type="checkbox"
        checked={checked}
        className="size-6 shrink-0 accent-primary"
        onChange={(event) => {
          onChange(event.target.checked);
        }}
      />
      <Label htmlFor="show-passwords" className="text-body-md font-normal">
        {t("auth.password.show")}
      </Label>
    </div>
  );
}
