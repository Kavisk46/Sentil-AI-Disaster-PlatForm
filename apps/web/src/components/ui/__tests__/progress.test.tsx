import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Progress } from "@/components/ui/progress";

describe("Progress", () => {
  it("reports a real aria-valuenow for a known fraction", () => {
    render(<Progress value={0.75} />);
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "75");
  });

  it("omits aria-valuenow when indeterminate, rather than reporting a fabricated value", () => {
    render(<Progress indeterminate />);
    expect(screen.getByRole("progressbar")).not.toHaveAttribute("aria-valuenow");
  });

  it("omits aria-valuenow when no value has been reported yet", () => {
    render(<Progress value={null} />);
    expect(screen.getByRole("progressbar")).not.toHaveAttribute("aria-valuenow");
  });

  it("clamps out-of-range fractions instead of reporting an invalid percentage", () => {
    render(<Progress value={1.4} />);
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "100");
  });
});
