import { describe, expect, it } from "vitest";

import { formatBytes } from "@/lib/format";

describe("formatBytes", () => {
  it("formats bytes below 1 KB with no decimal", () => {
    expect(formatBytes(512)).toBe("512 B");
  });

  it("formats kilobytes with one decimal place", () => {
    expect(formatBytes(1536)).toBe("1.5 KB");
  });

  it("formats megabytes with one decimal place", () => {
    expect(formatBytes(5 * 1024 * 1024)).toBe("5.0 MB");
  });

  it("drops the decimal once the value reaches double digits", () => {
    expect(formatBytes(12 * 1024)).toBe("12 KB");
  });
});
