import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { UploadPanel } from "@/components/command-center/upload-panel";

const noop = () => {};

describe("UploadPanel", () => {
  it("idle state: renders the shared dropzone and forwards a valid file", () => {
    const onFileSelected = vi.fn();
    render(
      <UploadPanel
        isDemoMode={false}
        hasActiveAnalysis={false}
        state="idle"
        failure={null}
        uploadProgress={null}
        uploadErrorMessage={null}
        onFileSelected={onFileSelected}
        onReset={noop}
      />,
    );

    const dropzone = screen.getByRole("button", {
      name: /upload a satellite or disaster image/i,
    });
    const file = new File(["x"], "aerial.png", { type: "image/png" });
    const input = dropzone.querySelector("input[type=file]") as HTMLInputElement;
    fireEvent.change(input, { target: { files: [file] } });

    expect(onFileSelected).toHaveBeenCalledWith(file);
  });

  it("uploading state: shows the analysis-state indicator instead of the dropzone", () => {
    render(
      <UploadPanel
        isDemoMode={false}
        hasActiveAnalysis={true}
        state="uploading"
        failure={null}
        uploadProgress={0.4}
        uploadErrorMessage={null}
        onFileSelected={noop}
        onReset={noop}
      />,
    );

    expect(screen.getByText("Uploading satellite imagery...")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /upload a satellite/i })).not.toBeInTheDocument();
  });

  it("demo mode: disables upload entirely", () => {
    render(
      <UploadPanel
        isDemoMode={true}
        hasActiveAnalysis={false}
        state="idle"
        failure={null}
        uploadProgress={null}
        uploadErrorMessage={null}
        onFileSelected={noop}
        onReset={noop}
      />,
    );

    expect(screen.getByText(/demo mode is active/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /upload a satellite/i })).not.toBeInTheDocument();
  });

  it("completed state: shows a reset control that calls onReset", () => {
    const onReset = vi.fn();
    render(
      <UploadPanel
        isDemoMode={false}
        hasActiveAnalysis={true}
        state="completed"
        failure={null}
        uploadProgress={null}
        uploadErrorMessage={null}
        onFileSelected={noop}
        onReset={onReset}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /new analysis/i }));
    expect(onReset).toHaveBeenCalled();
  });
});
