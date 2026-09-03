import type { ComponentProps, MouseEvent } from "react";
import { Link, useLocation, useResolvedPath } from "react-router-dom";

import { useMorphNavigate } from "@/lib/motion";

/**
 * A link that hands the navigation to a view transition.
 *
 * It stays an anchor -- middle click, ctrl-click and "open in new tab" are how
 * people move around, and a div with an onClick takes all three away. Only the
 * plain left click is intercepted, which is the one that stays on this page.
 */
export function MorphLink({ to, onClick, ...props }: ComponentProps<typeof Link>) {
  const navigate = useMorphNavigate();
  const here = useLocation();
  const target = useResolvedPath(to);

  // Clicking the logo while looking at the home page, or the section you are
  // already reading, is not a change. Animated anyway it is the worst thing
  // this screen can do: one copy of the page leaves upwards while an identical
  // copy arrives from below, and for a moment the whole thing is doubled
  // against itself.
  const arrived = target.pathname === here.pathname && target.search === here.search;

  return (
    <Link
      to={to}
      onClick={(event: MouseEvent<HTMLAnchorElement>) => {
        onClick?.(event);
        if (
          event.defaultPrevented ||
          event.button !== 0 ||
          event.metaKey ||
          event.ctrlKey ||
          event.shiftKey ||
          event.altKey
        ) {
          return;
        }
        event.preventDefault();
        if (arrived) return;
        void navigate(to);
      }}
      {...props}
    />
  );
}
