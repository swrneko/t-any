import { Monitor, Moon, Sun } from "lucide-react";
import { useTranslation } from "react-i18next";

import { THEMES, useTheme, type Theme } from "@/components/ThemeProvider";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { morphTheme, revealFrom } from "@/lib/motion";

const ICONS: Record<Theme, typeof Sun> = {
  light: Sun,
  dark: Moon,
  system: Monitor,
};

export function ThemeSwitch() {
  const { t } = useTranslation();
  const { theme, setTheme, resolved } = useTheme();

  // The button shows what you are looking at, the menu shows what you picked:
  // under "system" those differ, and hiding that makes the control feel broken.
  const Current = resolved === "dark" ? Moon : Sun;

  /** The new palette opens as a circle from the control that asked for it, so
   *  the change reads as one thing spreading rather than the page blinking. */
  const pick = (option: Theme, event: Event) => {
    const box = (event.currentTarget as HTMLElement | null)?.getBoundingClientRect();
    if (box) {
      revealFrom({ clientX: box.left + box.width / 2, clientY: box.top + box.height / 2 });
    }
    void morphTheme(() => setTheme(option));
  };

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon-sm" aria-label={t("theme.label")}>
          <Current className="size-4" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        {THEMES.map((option) => {
          const Icon = ICONS[option];
          return (
            <DropdownMenuItem
              key={option}
              onSelect={(event) => pick(option, event)}
              className={option === theme ? "bg-accent text-accent-foreground" : undefined}
            >
              <Icon className="size-4" />
              {t(`theme.${option}`)}
            </DropdownMenuItem>
          );
        })}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
