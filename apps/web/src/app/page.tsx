import { redirect } from "next/navigation";

/**
 * The engineering foundation ships no marketing/landing content — the root
 * route simply forwards to the dashboard shell that later sprints build
 * out.
 */
export default function RootPage() {
  redirect("/dashboard");
}
