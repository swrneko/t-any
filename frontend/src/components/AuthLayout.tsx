import { AudioLines } from "lucide-react";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { LanguageSwitch } from "@/components/LanguageSwitch";
import { ThemeSwitch } from "@/components/ThemeSwitch";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

interface AuthLayoutProps {
  title: string;
  subtitle?: string;
  children: ReactNode;
}

export function AuthLayout({ title, subtitle, children }: AuthLayoutProps) {
  const { t } = useTranslation();

  return (
    <div className="relative grid min-h-dvh place-items-center overflow-hidden p-4">
      <div
        aria-hidden
        className="pointer-events-none absolute inset-x-0 top-0 h-[60vh] bg-[radial-gradient(120%_80%_at_50%_0%,var(--primary),transparent_70%)] opacity-15"
      />

      <div className="relative w-full max-w-md">
        <div className="mb-4 flex items-center justify-between">
          <span className="flex items-center gap-2 text-sm font-medium tracking-tight text-muted-foreground">
            <span className="grid size-7 place-items-center rounded-md bg-primary text-primary-foreground">
              <AudioLines className="size-4" />
            </span>
            {t("app.name")}
          </span>
          <div className="flex items-center gap-1">
            <LanguageSwitch />
            <ThemeSwitch />
          </div>
        </div>

        <Card className="shadow-lg">
          <CardHeader>
            <CardTitle className="text-2xl">{title}</CardTitle>
            {subtitle && <CardDescription>{subtitle}</CardDescription>}
          </CardHeader>
          <CardContent>{children}</CardContent>
        </Card>
      </div>
    </div>
  );
}
