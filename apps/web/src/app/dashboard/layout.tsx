"use client";

import { Menu } from "lucide-react";

import { Button } from "@/components/ui/button";
import { ThemeToggle } from "@/components/theme-toggle";
import { useUiStore } from "@/store/ui-store";

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const isSidebarOpen = useUiStore((state) => state.isSidebarOpen);
  const toggleSidebar = useUiStore((state) => state.toggleSidebar);

  return (
    <div className="flex min-h-full flex-1">
      <aside
        className={`border-r bg-card transition-all duration-200 ${
          isSidebarOpen ? "w-64" : "w-0 overflow-hidden"
        }`}
      >
        <div className="p-4 text-sm font-semibold tracking-tight">SentinelAI</div>
      </aside>

      <div className="flex flex-1 flex-col">
        <header className="flex h-14 items-center justify-between border-b px-4">
          <Button variant="ghost" size="icon" aria-label="Toggle sidebar" onClick={toggleSidebar}>
            <Menu />
          </Button>
          <ThemeToggle />
        </header>

        <main className="flex flex-1 flex-col p-6">{children}</main>
      </div>
    </div>
  );
}
