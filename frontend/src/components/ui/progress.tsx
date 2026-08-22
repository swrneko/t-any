import * as React from "react"
import { Progress as ProgressPrimitive } from "radix-ui"

import { cn } from "@/lib/utils"

// `indeterminate` is added on top of the shadcn default: work here reports no
// percentage until the first chunk comes back, and a bar frozen at zero reads
// as "stuck" rather than "starting".
function Progress({
  className,
  value,
  indeterminate,
  ...props
}: React.ComponentProps<typeof ProgressPrimitive.Root> & { indeterminate?: boolean }) {
  return (
    <ProgressPrimitive.Root
      data-slot="progress"
      value={indeterminate ? null : value}
      className={cn(
        "relative h-2 w-full overflow-hidden rounded-full bg-primary/20",
        className
      )}
      {...props}
    >
      <ProgressPrimitive.Indicator
        data-slot="progress-indicator"
        className={cn(
          "h-full w-full flex-1 bg-primary transition-all",
          indeterminate && "w-1/3 flex-none animate-progress-slide"
        )}
        style={indeterminate ? undefined : { transform: `translateX(-${100 - (value || 0)}%)` }}
      />
    </ProgressPrimitive.Root>
  )
}

export { Progress }
