import { cn } from "@/lib/utils"

function Skeleton({ className, ...props }: React.ComponentProps<"div">) {
  return (
    // A light sweeping across, rather than the whole block breathing: it says
    // "loading" in the same language the rest of the app moves in.
    <div
      data-slot="skeleton"
      className={cn(
        "relative overflow-hidden rounded-lg bg-accent/60",
        "after:absolute after:inset-0 after:animate-sheen after:bg-linear-to-r after:from-transparent after:via-glass-raised after:to-transparent",
        className
      )}
      {...props}
    />
  )
}

export { Skeleton }
