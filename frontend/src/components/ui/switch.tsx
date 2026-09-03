"use client"

import * as React from "react"
import { Switch as SwitchPrimitive } from "radix-ui"

import { cn } from "@/lib/utils"

/** Material's switch, with the disc one size in both states: growing on the way
 *  across gives the eye a second thing to follow over a distance that is only
 *  worth following once. */
function Switch({
  className,
  size = "default",
  ...props
}: React.ComponentProps<typeof SwitchPrimitive.Root> & {
  size?: "sm" | "default"
}) {
  return (
    <SwitchPrimitive.Root
      data-slot="switch"
      data-size={size}
      className={cn(
        // Same duration as the thumb: the track filling in after the disc has
        // already arrived is the two halves of one control disagreeing.
        "peer group/switch inline-flex shrink-0 items-center rounded-full border-2 border-transparent transition-colors duration-(--motion-control) ease-standard outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50 disabled:cursor-not-allowed disabled:opacity-50",
        "data-[size=default]:h-6 data-[size=default]:w-11 data-[size=sm]:h-4 data-[size=sm]:w-7",
        "data-[state=checked]:bg-primary data-[state=unchecked]:bg-input dark:data-[state=unchecked]:bg-input/80",
        className
      )}
      {...props}
    >
      <SwitchPrimitive.Thumb
        data-slot="switch-thumb"
        className={cn(
          "pointer-events-none block rounded-full bg-background shadow-elevation-1 ring-0",
          // Only the compositor properties are animated. `width` and `height`
          // used to be in this list, and a disc that changes size by changing
          // its box relayouts the track on every frame -- that is what made
          // the thumb stutter across instead of gliding.
          //
          // The crossing is deliberately NOT the spring. That curve is at 93.8%
          // of the distance by 16.7% of its duration, so the thumb jumped and
          // then hung around the far end wobbling; what reads as weight on a
          // panel reads as a flinch on something this small. `emphasized`
          // leaves with a zero slope, so the move starts from rest.
          //
          // `--motion-control`, not short: the disc crosses a fifth of an inch
          // and at 150ms that is a flick you notice having happened rather than
          // a movement you watch.
          "transition-[translate,scale] duration-(--motion-control) ease-emphasized",
          // The box is the full height of the track and the disc is drawn
          // inside it at a fixed fraction, so the gap around it is the same in
          // both states and nothing about the disc changes but where it is.
          "group-data-[size=default]/switch:size-5 group-data-[size=default]/switch:[--thumb-grow:0.8]",
          "group-data-[size=sm]/switch:size-3 group-data-[size=sm]/switch:[--thumb-grow:0.833]",
          // Offsets assume the disc scales from its centre: at 0.8 a 20px disc
          // shows as 16px centred in its own box, which puts its visible edge
          // 2px in without translating for it -- the same 2px it lands on at
          // the far end, so the two states are mirrors.
          "group-data-[size=default]/switch:data-[state=unchecked]:translate-x-0 group-data-[size=default]/switch:data-[state=checked]:translate-x-5",
          "group-data-[size=sm]/switch:data-[state=unchecked]:translate-x-0 group-data-[size=sm]/switch:data-[state=checked]:translate-x-3",
          // One origin for both states. Switching it between left and right is
          // what made the thumb lurch backwards before setting off:
          // `transform-origin` cannot be transitioned, so a scaled disc jumped
          // the width of its own margin the instant the state flipped.
          // Centred, the squash spreads both ways, so it is gentler than the
          // old edge-anchored stretch and still clears the track.
          "origin-center",
          "[--squash-x:1] [--squash-y:1]",
          "group-active/switch:[--squash-x:1.08] group-active/switch:[--squash-y:0.94]",
          "[scale:calc(var(--thumb-grow)*var(--squash-x))_calc(var(--thumb-grow)*var(--squash-y))]",
          "dark:data-[state=checked]:bg-primary-foreground dark:data-[state=unchecked]:bg-foreground"
        )}
      />
    </SwitchPrimitive.Root>
  )
}

export { Switch }
