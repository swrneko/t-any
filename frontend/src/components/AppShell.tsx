import { AudioLines, History, LogOut, Settings, ShieldAlert } from "lucide-react";
import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { useLocation } from "react-router-dom";

import { LanguageSwitch } from "@/components/LanguageSwitch";
import { MorphLink } from "@/components/MorphLink";
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

/**
 * Where a screen hangs controls that belong to the bar rather than to the page.
 *
 * A transcript's player, its find bar and its export buttons all have to stay
 * on screen while nine hundred lines go past, and a second sticky surface an
 * inch below the first is two surfaces however carefully they are aligned: two
 * borders, two shadows, two lit edges, and a seam between them where the page
 * shows through. Being one element is not a matter of matching them up. So the
 * screen renders its controls through here and they land inside the bar's own
 * island -- one glass, one edge, one shadow, and the bar simply reaches further
 * down while that screen is open.
 */
const BarSlot = createContext<HTMLElement | null>(null);

export function useBarSlot(): HTMLElement | null {
  return useContext(BarSlot);
}

export function AppShell({ authMode, onLogout, children }: AppShellProps) {
  const { t } = useTranslation();
  const { pathname } = useLocation();
  const screen = pathname.split("/")[1] ?? "";
  const lifted = useScrolled();
  const [slot, setSlot] = useState<HTMLDivElement | null>(null);

  return (
    <div className="min-h-dvh">
      {/* The bar is an island: a surface of its own, floating clear of the top
          edge with the page passing behind and under it rather than stopping at
          a line drawn across the window. The header itself is only the gutter
          that holds it there -- nothing is painted on it, so the grid and the
          light run past on both sides.

          It is a surface at rest as well now. A band that only appears once the
          page has moved is honest for a bar welded to the top edge, where glass
          over nothing is a grey stripe; an island that is invisible until you
          scroll is not an island. What scrolling changes is the weight: the
          resting glass becomes the raised one, which is thicker, blurs further
          and sits on a deeper shadow. */}
      {/* Fixed rather than sticky, and that is load-bearing now. A sticky header
          is in the flow, so the bar growing to take a screen's controls would
          push the whole page down by their height -- and the mark that decides
          when to dock would go down with it, back below the line, undock, come
          back up, and dock again. Out of the flow the bar can be any height it
          likes and nothing under it moves; `main` carries the clearance
          instead, as a constant rather than as whatever the bar happens to be,
          which also settles the eight pixels the page used to jump the first
          time you scrolled. */}
      <header data-bar className="fixed inset-x-0 top-0 z-40 px-4 pt-3">
        <div
          className={cn(
            // The radius is not in the transition list, and cannot usefully be:
            // a pill is `9999px`, so interpolating to twenty-eight spends the
            // whole duration in shapes that all look identical and does the one
            // visible step at the end. It changes with the screen instead,
            // which is where every other change on a navigation happens.
            "mx-auto w-full max-w-4xl overflow-hidden rounded-full border transition-[background-color,border-color,box-shadow,backdrop-filter] duration-(--motion-medium) ease-emphasized",
            // Thinner than the glass it is made of. The bar is the one surface
            // with a whole page travelling under it, so it is the one place
            // where seeing through is worth more than reading against a settled
            // fill -- and it still thickens when there is something to be read
            // against.
            lifted ? "glass-raised bg-glass-raised/55" : "glass bg-glass/40",
          )}
        >
          <div
            className={cn(
              "flex items-center gap-2 px-3 transition-[height] duration-(--motion-medium) ease-emphasized",
              lifted ? "h-14" : "h-16",
            )}
          >
          <MorphLink
            to="/"
            className="group mr-auto flex items-center gap-2.5 rounded-full font-semibold tracking-tight outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50"
          >
            <span className="grid size-8 place-items-center rounded-full bg-primary text-primary-foreground shadow-elevation-2 transition-transform duration-(--motion-medium) ease-spring group-hover:scale-110 group-hover:-rotate-6">
              <AudioLines className="size-4.5" />
            </span>
            {t("app.name")}
          </MorphLink>

          {/* The archive is where searching happens, but a magnifier said
              "search" and not "the recordings you already have" -- and the
              search box is on that page anyway, where it can be seen. Each
              button now draws the place it opens: what has already been, and
              the machine's own settings. */}
          <NavButton to="/history" label={t("history.title")} active={pathname === "/history"}>
            <History className="size-4" />
          </NavButton>

          <NavButton
            to="/settings"
            label={t("settings.title")}
            active={pathname.startsWith("/settings")}
          >
            <Settings className="size-4" />
          </NavButton>

          <LanguageSwitch />
          <ThemeSwitch />

          {authMode === "builtin" && (
            <Button variant="ghost" size="icon-sm" aria-label={t("home.logout")} onClick={onLogout}>
              <LogOut className="size-4" />
            </Button>
          )}
          </div>

          {/* Whatever the screen put here, drawn as part of this surface. Empty
              on every screen but one, and then it takes up no room at all. */}
          <div data-bar-extra ref={setSlot} className="empty:hidden" />
        </div>
      </header>

      {/* The screen fades itself in when it arrives, and that is the whole of a
          page change. `key` is what makes it an arrival: without it React keeps
          this element across routes and there is nothing for an entry animation
          to attach to. Only the first segment of the address, so walking
          between settings sections does not tear the shell down -- the section
          does its own fade, one level in.

          The old screen is not faded out. It is simply gone, which is why two
          screens are never both on the window and never both legible -- the
          doubling that a cross-fade produces cannot happen here. */}
      <main
        key={screen}
        // Twelve of gutter plus the resting bar's sixty-four, and then the
        // page's own eight -- which is exactly where the content sat when the
        // header was still taking up room.
        className="mx-auto grid w-full max-w-4xl animate-page-in gap-6 px-4 pt-27 pb-8"
      >
        {authMode === "disabled" && (
          <Alert variant="warning">
            <ShieldAlert />
            <AlertDescription>{t("authDisabled.banner")}</AlertDescription>
          </Alert>
        )}
        <BarSlot.Provider value={slot}>{children}</BarSlot.Provider>
      </main>
    </div>
  );
}

/** The highlight is switched off here and on over there, and is not a thing
 *  that travels. It was, and travelling is what a named element does badly
 *  here: naming the background alone painted it above the icon it sits behind,
 *  because a named element is lifted out of the picture it was drawn in and
 *  drawn over the top of it; naming the whole control fixed that and took the
 *  icon with it, so the button being walked to lost its icon from the bar --
 *  it is only in the picture that is still in flight -- and reappeared when
 *  the pill landed. Both readings are the same defect: a control cannot be in
 *  two pictures at once, so the one it left goes blank for the length of the
 *  trip. Unnamed, both buttons stay in the bar's own cross-fade and one
 *  highlight fades out while the other fades in, which is what actually
 *  happened. */
function NavButton({
  to,
  label,
  active,
  children,
}: {
  to: string;
  label: string;
  active: boolean;
  children: ReactNode;
}) {
  return (
    <Button
      asChild
      variant="ghost"
      size="icon-sm"
      aria-label={label}
      className={cn(active && "text-accent-foreground")}
    >
      <MorphLink to={to}>
        {active && (
          <span aria-hidden className="absolute inset-0 -z-10 rounded-full bg-accent" />
        )}
        {children}
      </MorphLink>
    </Button>
  );
}

/** Whether the page has moved at all. The bar reacts to that and nothing else,
 *  so the listener can be passive and the state a single boolean. */
function useScrolled(): boolean {
  // Read before the first paint, not after it. A reload restores the scroll
  // position, so a bar that starts out believing it is at the top spends its
  // first frames animating down to where it should already have been -- on
  // every refresh, over whatever else the page is doing at the time.
  const [scrolled, setScrolled] = useState(() => window.scrollY > 8);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 8);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return scrolled;
}
