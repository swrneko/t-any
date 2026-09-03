import * as React from "react"
import { Slider as SliderPrimitive } from "radix-ui"

import { cn } from "@/lib/utils"

/**
 * A value chosen along a line: where the playhead is, how loud it is.
 *
 * The track is the same hairline the progress bar draws, because they are the
 * same thing seen twice -- one reports a position and one sets it. What
 * separates them is the handle, and the handle is one size in every state: it
 * is the one thing on the line small enough that growing it would be read as
 * the line moving rather than as the handle answering. The press is answered by
 * the halo instead, which costs no layout and cannot be mistaken for travel.
 */
function Slider({
  className,
  // The handle is the control -- radix puts `role="slider"` on the thumb, not
  // on the root -- so a label written on the root would name nothing.
  "aria-label": label,
  "aria-valuetext": valueText,
  ...props
}: React.ComponentProps<typeof SliderPrimitive.Root>) {
  return (
    <SliderPrimitive.Root
      data-slot="slider"
      className={cn(
        "group/slider relative flex w-full touch-none items-center select-none data-[disabled]:pointer-events-none data-[disabled]:opacity-50",
        className
      )}
      {...props}
    >
      <SliderPrimitive.Track
        data-slot="slider-track"
        className="relative h-1 w-full grow overflow-hidden rounded-full bg-primary/20"
      >
        <SliderPrimitive.Range
          data-slot="slider-range"
          className="absolute h-full rounded-full bg-primary"
        />
      </SliderPrimitive.Track>
      <SliderPrimitive.Thumb
        data-slot="slider-thumb"
        aria-label={label}
        aria-valuetext={valueText}
        className="block size-3 shrink-0 rounded-full bg-primary shadow-elevation-1 transition-[box-shadow] duration-(--motion-control) ease-standard outline-none hover:ring-8 hover:ring-primary/15 focus-visible:ring-8 focus-visible:ring-primary/25"
      />
    </SliderPrimitive.Root>
  )
}

export { Slider }
