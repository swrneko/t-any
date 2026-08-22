import { AudioLines, LogOut, Search, ShieldAlert, SlidersHorizontal } from "lucide-react";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Link, useLocation } from "react-router-dom";

import { LanguageSwitch } from "@/components/LanguageSwitch";
import { ThemeSwitch } from "@/components/ThemeSwitch";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { AuthMode } from "@/api/client";

interface AppShellProps {
  authMode: AuthMode;
  onLogout: () => void;
  children: ReactNode;
}

export function AppShell({ authMode, onLogout, children }: AppShellProps) {
  const { t } = useTranslation();
  const { pathname } = useLocation();

  return (
    <div className="min-h-dvh">
      <header className="sticky top-0 z-40 border-b border-border/60 bg-background/80 backdrop-blur-xl">
        <div className="mx-auto flex h-16 w-full max-w-4xl items-center gap-2 px-4">
          <Link
            to="/"
            className="mr-auto flex items-center gap-2.5 rounded-lg font-semibold tracking-tight outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50"
          >
            <span className="grid size-8 place-items-center rounded-lg bg-primary text-primary-foreground shadow-xs">
              <AudioLines className="size-4.5" />
            </span>
            {t("app.name")}
          </Link>

          <Button
            asChild
            variant="ghost"
            size="icon-sm"
            aria-label={t("search.title")}
            className={cn(pathname === "/search" && "bg-accent text-accent-foreground")}
          >
            <Link to="/search">
              <Search className="size-4" />
            </Link>
          </Button>

          <Button
            asChild
            variant="ghost"
            size="sm"
            className={cn(pathname === "/presets" && "bg-accent text-accent-foreground")}
          >
            <Link to="/presets">{t("presets.title")}</Link>
          </Button>

          <Button
            asChild
            variant="ghost"
            size="icon-sm"
            aria-label={t("settings.title")}
            className={cn(pathname === "/settings" && "bg-accent text-accent-foreground")}
          >
            <Link to="/settings">
              <SlidersHorizontal className="size-4" />
            </Link>
          </Button>

          <LanguageSwitch />
          <ThemeSwitch />

          {authMode === "builtin" && (
            <Button variant="ghost" size="icon-sm" aria-label={t("home.logout")} onClick={onLogout}>
              <LogOut className="size-4" />
            </Button>
          )}
        </div>
      </header>

      <main className="mx-auto grid w-full max-w-4xl gap-6 px-4 py-8">
        {authMode === "disabled" && (
          <Alert variant="warning">
            <ShieldAlert />
            <AlertDescription>{t("authDisabled.banner")}</AlertDescription>
          </Alert>
        )}
        {children}
      </main>
    </div>
  );
}
