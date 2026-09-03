"use client"

import { CheckIcon } from "lucide-react"
import * as React from "react"
import { Checkbox as CheckboxPrimitive } from "radix-ui"

import { cn } from "@/lib/utils"

function Checkbox({ className, ...props }: React.ComponentProps<typeof CheckboxPrimitive.Root>) {
  return (
    <CheckboxPrimitive.Root
      data-slot="checkbox"
      className={cn(
        "peer group/checkbox size-[18px] shrink-0 rounded-[6px] border-2 border-input outline-none",
        "transition-[background-color,border-color,box-shadow,scale] duration-(--motion-medium) ease-spring active:scale-90",
        "focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50",
        "disabled:cursor-not-allowed disabled:opacity-50",
        "data-[state=checked]:border-primary data-[state=checked]:bg-primary data-[state=checked]:text-primary-foreground",
        className,
      )}
      {...props}
    >
      {/* Kept mounted so the tick has somewhere to grow from: an indicator that
          appears fully drawn is a state change, not a movement. */}
      <CheckboxPrimitive.Indicator
        forceMount
        data-slot="checkbox-indicator"
        className="flex items-center justify-center text-current transition-transform duration-(--motion-medium) ease-spring group-data-[state=unchecked]/checkbox:scale-0 group-data-[state=checked]/checkbox:scale-100"
      >
        <CheckIcon className="size-3.5" strokeWidth={3} />
      </CheckboxPrimitive.Indicator>
    </CheckboxPrimitive.Root>
  )
}

export { Checkbox }
