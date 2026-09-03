import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { Slot } from "radix-ui"

import { pressRipple } from "@/lib/motion"
import { cn } from "@/lib/utils"

const buttonVariants = cva(
  // A press is answered by the ink and by nothing else. It used to shrink the
  // button to 97% and let it grow back over a quarter of a second, which is
  // the page-shrinks complaint at the size of a control: the label is read, so
  // three percent off is three percent wrong, and the slow way back is what
  // read as the button lagging behind the finger rather than answering it.
  "ripple inline-flex shrink-0 items-center justify-center gap-2 rounded-full text-sm font-medium whitespace-nowrap transition-[background-color,border-color,box-shadow,color] duration-(--motion-medium) ease-emphasized-out outline-none select-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 disabled:pointer-events-none disabled:opacity-50 aria-invalid:border-destructive aria-invalid:ring-destructive/20 dark:aria-invalid:ring-destructive/40 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg]:transition-transform [&_svg]:duration-(--motion-medium) [&_svg]:ease-spring [&_svg:not([class*='size-'])]:size-4",
  {
    variants: {
      variant: {
        default:
          "bg-primary text-primary-foreground shadow-elevation-1 hover:bg-primary/92 hover:shadow-elevation-2 active:shadow-elevation-1",
        destructive:
          "bg-destructive text-white shadow-elevation-1 hover:bg-destructive/90 hover:shadow-elevation-2 focus-visible:ring-destructive/20 dark:bg-destructive/60 dark:focus-visible:ring-destructive/40",
        // The outlined button is where the glass shows on a control: a hairline
        // and whatever is behind it, until the pointer arrives and it fills.
        // `glass-control`, not `glass` -- at this height the bevel's return
        // light sits against the hairline and reads as a second border.
        outline:
          "glass-control border text-foreground hover:bg-accent/70 hover:text-accent-foreground hover:shadow-elevation-3",
        secondary:
          "bg-secondary text-secondary-foreground hover:bg-secondary/80 hover:shadow-elevation-1",
        ghost:
          "hover:bg-accent/70 hover:text-accent-foreground dark:hover:bg-accent/50",
        link: "text-primary underline-offset-4 hover:underline after:hidden",
      },
      size: {
        default: "h-9 px-5 has-[>svg]:px-4",
        xs: "h-6 gap-1 px-2.5 text-xs has-[>svg]:px-2 [&_svg:not([class*='size-'])]:size-3",
        sm: "h-8 gap-1.5 px-4 has-[>svg]:px-3",
        lg: "h-11 px-7 has-[>svg]:px-5",
        icon: "size-9",
        "icon-xs": "size-6 [&_svg:not([class*='size-'])]:size-3",
        "icon-sm": "size-8",
        "icon-lg": "size-10",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
)

function Button({
  className,
  variant = "default",
  size = "default",
  asChild = false,
  onPointerDown,
  ...props
}: React.ComponentProps<"button"> &
  VariantProps<typeof buttonVariants> & {
    asChild?: boolean
  }) {
  const Comp = asChild ? Slot.Root : "button"

  return (
    <Comp
      data-slot="button"
      data-variant={variant}
      data-size={size}
      className={cn(buttonVariants({ variant, size, className }))}
      // The ink is drawn by CSS from coordinates set here, so a press shows
      // immediately even if what it triggers takes a moment.
      onPointerDown={(event: React.PointerEvent<HTMLButtonElement>) => {
        if (variant !== "link") pressRipple(event)
        onPointerDown?.(event)
      }}
      {...props}
    />
  )
}

export { Button, buttonVariants }
