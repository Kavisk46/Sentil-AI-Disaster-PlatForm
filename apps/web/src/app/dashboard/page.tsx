"use client";

import { useApiHealth } from "@/hooks/use-api-health";

/**
 * Intentionally empty beyond a system-status check: this sprint delivers
 * the dashboard shell (layout, providers, state) only. Incident maps,
 * damage overlays, and briefings are out of scope until later phases (see
 * PROJECT_ROADMAP.md).
 */
export default function DashboardPage() {
  const { data, isPending, isError, error } = useApiHealth();

  return (
    <div className="flex flex-1 flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Dashboard</h1>
        <p className="text-muted-foreground text-sm">
          This is an empty foundation shell. Operational views will be added in later sprints.
        </p>
      </div>

      <div className="max-w-sm rounded-lg border bg-card p-4">
        <h2 className="text-sm font-medium">Backend status</h2>
        <p className="mt-1 text-sm">
          {isPending && <span className="text-muted-foreground">Checking API...</span>}
          {isError && <span className="text-destructive">Unreachable: {error.message}</span>}
          {data && <span className="text-emerald-600 dark:text-emerald-500">{data.status}</span>}
        </p>
      </div>
    </div>
  );
}
