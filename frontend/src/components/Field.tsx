import { useId, type ReactNode } from "react";

import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

interface FieldProps {
  label: string;
  /** Shown under the control; reserve the row even when empty so that a
   *  validation message appearing does not shift the form downwards. */
  hint?: ReactNode;
  invalid?: boolean;
  children: (id: string) => ReactNode;
}

export function Field({ label, hint, invalid, children }: FieldProps) {
  const id = useId();

  return (
    <div className="grid gap-2">
      <Label htmlFor={id} className={cn(invalid && "text-destructive")}>
        {label}
      </Label>
      {children(id)}
      {hint !== undefined && (
        <p className={cn("min-h-4 text-xs", invalid ? "text-destructive" : "text-muted-foreground")}>
          {hint}
        </p>
      )}
    </div>
  );
}
