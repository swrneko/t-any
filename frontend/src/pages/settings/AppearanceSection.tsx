import { useTranslation } from "react-i18next";

import { LanguageSwitch } from "@/components/LanguageSwitch";
import { ThemeSwitch } from "@/components/ThemeSwitch";
import { Label } from "@/components/ui/label";

/**
 * The same two controls the header carries, given room and a label.
 *
 * They stay in the header as well, because the language has to be changeable on
 * the login screen, where no settings page is reachable. Both live in the
 * browser rather than in the database: the theme has to apply before the first
 * request, or a dark instance flashes white on every load.
 */
export function AppearanceSection() {
  const { t } = useTranslation();

  return (
    <div className="grid gap-6">
      <h2 className="text-lg font-semibold tracking-tight">
        {t("settings.sections.appearance")}
      </h2>

      <div className="flex items-center justify-between gap-4">
        <Label className="font-normal">{t("theme.label")}</Label>
        <ThemeSwitch />
      </div>

      <div className="flex items-center justify-between gap-4">
        <Label className="font-normal">{t("language.label")}</Label>
        <LanguageSwitch />
      </div>

      <p className="text-sm text-muted-foreground">{t("settings.appearance.dates")}</p>
    </div>
  );
}
