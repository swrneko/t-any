import { Languages } from "lucide-react";
import { useTranslation } from "react-i18next";

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { SUPPORTED_LANGUAGES } from "@/i18n";

export function LanguageSwitch() {
  const { i18n, t } = useTranslation();
  const current = SUPPORTED_LANGUAGES.find((lng) => i18n.resolvedLanguage === lng) ?? "en";

  return (
    <Select value={current} onValueChange={(value) => void i18n.changeLanguage(value)}>
      <SelectTrigger
        size="sm"
        aria-label={t("language.label")}
        className="gap-2 border-transparent bg-transparent shadow-none hover:bg-accent dark:bg-transparent dark:hover:bg-accent"
      >
        <Languages className="size-4 opacity-70" />
        <SelectValue />
      </SelectTrigger>
      <SelectContent align="end">
        {SUPPORTED_LANGUAGES.map((lng) => (
          <SelectItem key={lng} value={lng}>
            {t(`language.${lng}`)}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
