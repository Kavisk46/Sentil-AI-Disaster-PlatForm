import { TopBar } from "@/components/command-center/top-bar";

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-full flex-1 flex-col">
      <TopBar />
      <main className="flex flex-1 flex-col">{children}</main>
    </div>
  );
}
