import { cva } from "class-variance-authority";
import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold transition-colors",
  {
    variants: {
      variant: {
        default:   "border-transparent bg-primary/20 text-primary",
        secondary: "border-transparent bg-secondary text-secondary-foreground",
        destructive: "border-transparent bg-destructive/20 text-destructive-foreground",
        outline:   "text-foreground",
        pending:   "status-pending",
        running:   "status-running",
        completed: "status-completed",
        failed:    "status-failed",
        info:      "bg-blue-500/15 text-blue-400 border-blue-500/30",
        warning:   "bg-yellow-500/15 text-yellow-400 border-yellow-500/30",
        success:   "bg-emerald-500/15 text-emerald-400 border-emerald-500/30",
        error:     "bg-red-500/15 text-red-400 border-red-500/30",
      },
    },
    defaultVariants: { variant: "default" },
  }
);

function Badge({ className, variant, ...props }) {
  return (
    <div className={cn(badgeVariants({ variant }), className)} {...props} />
  );
}

export { Badge, badgeVariants };
