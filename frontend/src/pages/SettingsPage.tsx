import { HardDrive, KeyRound, Palette, Server, Sparkles, Users } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Outlet, useLocation } from "react-router-dom";

import { MorphLink } from "@/components/MorphLink";
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

  // The section, not the address. `/settings` is a real render before it is a
  // redirect: the index route is a `<Navigate>`, so the panel mounts once with
  // nothing in it, fades in empty, and mounts again a tick later with the
  // section that was meant. Keyed on the address that is two blinks on every
  // arrival here and two more every time the gear is pressed again. Keyed on
  // the section it resolves to, `/settings` and `/settings/users` are the same
  // key and there is one arrival, which is what happened.
  const section = pathname.split("/")[2] || "users";

  return (
    <div className="grid gap-6">
      <h1 className="text-2xl font-semibold tracking-tight">{t("settings.title")}</h1>

      <div className="grid gap-6 md:grid-cols-[13rem_1fr]">
        {/* Unnamed, and it does not need to be: walking from one section to the
            next animates the panel on the right and nothing else, so this
            column is simply still there afterwards. `self-start` stays, for
            the plain reason it was worth having anyway -- a grid item stretches
            to its row, and six links in a box as tall as whichever section it
            happens to sit beside is a box with a lot of nothing under it. */}
        <nav data-panel className="panel grid content-start gap-1 self-start rounded-xl p-2">
          {sections.map(({ path, Icon }) => {
            const here = pathname.startsWith(`/settings/${path}`);
            return (
              <Button
                key={path}
                asChild
                variant="ghost"
                size="sm"
                className={cn("justify-start", here && "text-accent-foreground")}
              >
                {/* No name here, deliberately: see the note on `NavButton`.
                    A highlight that travels has to be lifted out of this list,
                    and whatever is lifted is missing from the list for the
                    length of the trip -- so the section being walked to lost
                    its own label until the pill carrying it arrived. The list
                    keeps every row, and the highlight fades from one to the
                    next inside the list's own cross-fade. */}
                <MorphLink to={path}>
                  {here && (
                    <span aria-hidden className="absolute inset-0 -z-10 rounded-full bg-accent" />
                  )}
                  <Icon className="size-4" />
                  {t(`settings.sections.${path}`)}
                </MorphLink>
              </Button>
            );
          })}
        </nav>

        {/* One block per section, rather than a heading and a sentence loose on
            the background with the cards of the section floating under them.
            The panel says where the section begins and ends; the boxes inside
            it are divisions of it and are flattened to hairlines by the
            stylesheet, so nothing is drawn twice.

            Keyed on the section, so walking down the list fades these contents
            in without touching the list, the title or the shell around them --
            the only thing that changed is the only thing that moves. */}
        {/* The surface is not keyed and does not fade: it is the same panel
            before and after, and a surface that appears from nothing while its
            own height is still settling is the jerk this looked like. What is
            keyed is the contents, one level in, so the panel stands still and
            the section inside it arrives. It still changes height when the
            section's data lands -- that is the section loading, and it is the
            one movement here that is telling the truth. */}
        <div data-panel className="panel min-w-0 rounded-xl p-5">
          <div key={section} className="animate-page-in">
            <Outlet />
          </div>
        </div>
      </div>
    </div>
  );
}
