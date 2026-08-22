import { HardDrive, KeyRound, Palette, Server, Sparkles, Users } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Link, Outlet, useLocation } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const SECTIONS = [
  { path: "users", Icon: Users, adminOnly: false },
  { path: "storage", Icon: HardDrive, adminOnly: true },
  { path: "appearance", Icon: Palette, adminOnly: false },
  { path: "providers", Icon: Server, adminOnly: false },
  { path: "presets", Icon: Sparkles, adminOnly: false },
  { path: "api", Icon: KeyRound, adminOnly: false },
] as const;

/**
 * A shell, and one address per section.
 *
 * Tabs would have meant that a warning elsewhere in the app can only say "look
 * around in settings", that opening settings fetches all of them at once, and
 * that hiding an admin-only section is a condition inside a component rather
 * than a missing link.
 */
export function SettingsPage({ isAdmin }: { isAdmin: boolean }) {
  const { t } = useTranslation();
  const { pathname } = useLocation();
  const sections = SECTIONS.filter((section) => isAdmin || !section.adminOnly);

  return (
    <div className="grid gap-6">
      <h1 className="text-2xl font-semibold tracking-tight">{t("settings.title")}</h1>

      <div className="grid gap-6 md:grid-cols-[13rem_1fr]">
        <nav className="grid content-start gap-1">
          {sections.map(({ path, Icon }) => (
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
