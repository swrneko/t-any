import { KeyRound, Palette, Server, Sparkles } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Link, Outlet, useLocation } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const SECTIONS = [
  { path: "appearance", Icon: Palette },
  { path: "providers", Icon: Server },
  { path: "presets", Icon: Sparkles },
  { path: "api", Icon: KeyRound },
] as const;

/**
 * A shell, and one address per section.
 *
 * Tabs would have meant that a warning elsewhere in the app can only say "look
 * around in settings", that opening settings fetches all of them at once, and
 * that hiding an admin-only section is a condition inside a component rather
 * than a missing link.
 */
export function SettingsPage() {
  const { t } = useTranslation();
  const { pathname } = useLocation();

  return (
    <div className="grid gap-6">
      <h1 className="text-2xl font-semibold tracking-tight">{t("settings.title")}</h1>

      <div className="grid gap-6 md:grid-cols-[13rem_1fr]">
        <nav className="grid content-start gap-1">
          {SECTIONS.map(({ path, Icon }) => (
            <Button
              key={path}
              asChild
              variant="ghost"
              size="sm"
              className={cn(
                "justify-start",
                pathname.startsWith(`/settings/${path}`) && "bg-accent text-accent-foreground",
              )}
            >
              <Link to={path}>
                <Icon className="size-4" />
                {t(`settings.sections.${path}`)}
              </Link>
            </Button>
          ))}
        </nav>

        <div className="min-w-0">
          <Outlet />
        </div>
      </div>
    </div>
  );
}
