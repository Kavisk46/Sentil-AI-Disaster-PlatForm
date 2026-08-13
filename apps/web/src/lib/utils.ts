import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

/**
 * Merges conditional class names (clsx) and then resolves conflicting
 * Tailwind utility classes (tailwind-merge), so a consumer can override a
 * component's default classes (e.g. `<Button className="w-full" />`)
 * without fighting specificity.
 */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
