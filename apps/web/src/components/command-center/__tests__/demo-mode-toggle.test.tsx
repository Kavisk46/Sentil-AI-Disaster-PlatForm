import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { DemoModeToggle } from "@/components/command-center/demo-mode-toggle";
import { useIncidentStore } from "@/store/incident-store";

afterEach(() => {
  useIncidentStore.setState({ isDemoMode: false });
});

describe("DemoModeToggle", () => {
  it("is a real, keyboard-operable switch (role=switch), not a bare div", () => {
    render(<DemoModeToggle />);
    const toggle = screen.getByRole("switch", { name: /toggle demo mode/i });
    expect(toggle).toBeInTheDocument();
    expect(toggle).toHaveAttribute("aria-checked", "false");
  });

  it("flips the shared store's isDemoMode flag when toggled", () => {
    render(<DemoModeToggle />);
    const toggle = screen.getByRole("switch", { name: /toggle demo mode/i });

    fireEvent.click(toggle);

    expect(useIncidentStore.getState().isDemoMode).toBe(true);
    expect(toggle).toHaveAttribute("aria-checked", "true");
  });
});
