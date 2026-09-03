import { useCallback, type PointerEvent } from "react";
import { flushSync } from "react-dom";
import { useNavigate, type NavigateOptions, type To } from "react-router-dom";

/** The animations a transition takes over from. `rise` is everything that
 *  appears by itself; `ripple` is the press that started the change, which
 *  otherwise goes on spreading inside the new screen for as long again as the
 *  screen took to arrive. */
const SUPERSEDED = new Set(["rise", "ripple", "page-in"]);

/** Nothing here is required for the app to work: a browser without view
 *  transitions, or a person who asked for less motion, gets the same change of
 *  state without the animation over it. */
function animates(): boolean {
  return (
    typeof document !== "undefined" &&
    typeof document.startViewTransition === "function" &&
    !window.matchMedia("(prefers-reduced-motion: reduce)").matches
  );
}

/**
 * Run a state change inside a transition, with a flag on the root saying what
 * kind of change it is. The stylesheet reads that flag to decide what is
 * allowed to move, because a transition always captures the whole document
 * whether or not the change was worth capturing.
 *
 * The whole thing rests on the update landing in the DOM inside the callback:
 * the browser photographs the old frame, runs this, photographs the new one and
 * animates between the two. `flushSync` is what makes that true -- including
 * for a navigation, which is why the router is mounted with `useTransitions`
 * off in `App.tsx`. Left on, the address changes here and the screen does not,
 * and the browser ends up animating a page into itself.
 */
function transition(kind: Kind, update: () => void): Promise<void> {
  if (!animates()) {
    update();
    return Promise.resolve();
  }
  const root = document.documentElement;
  root.dataset[`${kind}Morph`] = "on";
  return document
    .startViewTransition(() => {
      flushSync(update);
      settle();
    })
    .finished.finally(() => {
      // The freeze outlives the morph by a frame. Everything the morph was
      // standing in for changes back on the tick the flag comes off -- and the
      // durations that were pinned at zero come back on that same tick, so
      // whatever changed starts easing instead of simply being what it is.
      // Two frames is what it takes for the new values to be painted first.
      root.dataset.settling = "on";
      delete root.dataset[`${kind}Morph`];
      requestAnimationFrame(() =>
        requestAnimationFrame(() => {
          delete root.dataset.settling;
        }),
      );
    });
}

type Kind = "quiet" | "theme";

/**
 * Whatever was arriving has arrived.
 *
 * A transition does not photograph the new state -- it renders it live inside
 * the snapshot -- so a row that mounts with an entry animation keeps playing it
 * there, rising on its own clock inside a page that is rising on another. Two
 * animations of the same movement disagreeing about when it ends is exactly
 * what reads as a stutter. The transition is the motion now, so anything that
 * was appearing -- or any ink still spreading from the press that caused all
 * this -- is moved to its last frame before the new state is captured.
 */
function settle(): void {
  for (const animation of document.documentElement.getAnimations({ subtree: true })) {
    if (animation instanceof CSSAnimation && SUPERSEDED.has(animation.animationName)) {
      animation.finish();
    }
  }
}

/**
 * A change inside one screen: a list reordering, a row leaving.
 *
 * Only the elements that carry a name move; the rest of the page is replaced
 * outright. Cross-fading a whole screen against itself is what turns a small
 * change into a redraw, with two versions of the interface visibly on top of
 * each other -- and everything below the change has moved, so they do not even
 * line up.
 */
export function morph(update: () => void): Promise<void> {
  return transition("quiet", update);
}

/** The palette changing, which is the one case where the whole picture is the
 *  thing being animated. */
export function morphTheme(update: () => void): Promise<void> {
  return transition("theme", update);
}

export type MorphOptions = NavigateOptions;

/**
 * Navigation, which opens no transition at all.
 *
 * The arriving screen brings itself in with a CSS animation -- see `page-in`.
 * A view transition photographs the whole document, background and all, and
 * then animates the photograph; every version of that was reported as
 * flickering or as the page arriving squashed, because a named box is
 * interpolated between the height it had and the height it will have and some
 * engines stretch the picture into it whatever `object-fit` says.
 *
 * A row opening its page was the last exception, on the reasoning that there
 * one thing really is travelling. It is the worst case of the same defect
 * rather than an exception to it: no box in this app changes size as much as a
 * 69-pixel row becoming a 250-pixel page, so no picture was stretched further.
 * A mount animation has no photograph and no box, so it has neither failure.
 *
 * This is left as a hook rather than folded back into `useNavigate` because
 * the two are not the same call -- `MorphLink` and every list row go through
 * here, and the next thing that wants a transition on a navigation should have
 * one place to argue with.
 */
export function useMorphNavigate() {
  const navigate = useNavigate();
  return useCallback(
    (to: To, options?: MorphOptions) => Promise.resolve(navigate(to, options)),
    [navigate],
  );
}

/**
 * Material's ink, spreading from where the pointer landed.
 *
 * Only the element's own custom properties are touched -- no children are
 * added -- so this survives `asChild`, where the element React renders is not
 * the one we get.
 */
export function pressRipple(event: PointerEvent<HTMLElement>): void {
  const target = event.currentTarget;
  const box = target.getBoundingClientRect();
  target.style.setProperty("--ripple-x", `${event.clientX - box.left}px`);
  target.style.setProperty("--ripple-y", `${event.clientY - box.top}px`);

  // Restarting rather than ignoring: a second press during the first ripple is
  // the case where the feedback matters most.
  delete target.dataset.ripple;
  void target.offsetWidth;
  target.dataset.ripple = "on";
}

/** Where a circle should open from, in the coordinates the reveal is drawn in. */
export function revealFrom(event: { clientX: number; clientY: number }): void {
  const root = document.documentElement;
  root.style.setProperty("--reveal-x", `${event.clientX}px`);
  root.style.setProperty("--reveal-y", `${event.clientY}px`);
}
