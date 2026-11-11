import { useTranslation } from "react-i18next";

import { CheckIcon } from "@/components/ui/icons";
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
      {/* Native: Radix's checkbox needs ResizeObserver inside a form. The
          input is the 44 px target; the box drawn over it is 24 px. */}
      <span className="relative inline-flex size-11 shrink-0 items-center justify-center">
        <input
          id="show-passwords"
          type="checkbox"
          checked={checked}
          className="peer absolute inset-0 size-11 cursor-pointer appearance-none rounded-md outline-hidden"
          onChange={(event) => {
            onChange(event.target.checked);
          }}
        />
        <span
          aria-hidden="true"
          className="pointer-events-none flex size-6 items-center justify-center rounded-[5px] border-2 border-input bg-input-background text-primary-foreground peer-checked:border-primary peer-checked:bg-primary peer-focus-visible:ring-[3px] peer-focus-visible:ring-ring peer-focus-visible:ring-offset-2 peer-focus-visible:ring-offset-background [&>svg]:hidden peer-checked:[&>svg]:block"
        >
          <CheckIcon className="size-4" />
        </span>
      </span>
      <Label htmlFor="show-passwords" className="text-body-md font-normal">
        {t("auth.password.show")}
      </Label>
    </div>
  );
}
