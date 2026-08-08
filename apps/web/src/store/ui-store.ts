import { create } from "zustand";

/**
 * Client-only UI state (e.g. sidebar collapsed/expanded) that does not
 * belong in server state (TanStack Query) or the URL. Kept as a single small
 * store for the foundation phase; split into separate stores if unrelated
 * concerns start accumulating here.
 */
interface UiState {
  isSidebarOpen: boolean;
  toggleSidebar: () => void;
  setSidebarOpen: (open: boolean) => void;
}

export const useUiStore = create<UiState>((set) => ({
  isSidebarOpen: true,
  toggleSidebar: () => set((state) => ({ isSidebarOpen: !state.isSidebarOpen })),
  setSidebarOpen: (open) => set({ isSidebarOpen: open }),
}));
