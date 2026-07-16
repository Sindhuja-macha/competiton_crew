import { clsx } from "clsx";
import { twMerge } from "tailwind-merge";

/**
 * Merge Tailwind classes safely, resolving conflicts.
 * Drop-in equivalent of the ShadCN `cn` utility.
 */
export function cn(...inputs) {
  return twMerge(clsx(inputs));
}
