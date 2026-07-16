import { cn } from "@/lib/utils";

/**
 * Skeleton loader — renders a pulsing placeholder block.
 * Drop-in ShadCN-compatible implementation.
 */
function Skeleton({ className, ...props }) {
  return (
    <div
      className={cn(
        "animate-pulse rounded-lg bg-muted/40",
        className
      )}
      {...props}
    />
  );
}

export { Skeleton };
