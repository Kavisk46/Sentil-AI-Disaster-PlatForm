import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { UploadPanel } from "@/components/command-center/upload-panel";

const noop = () => {};

describe("UploadPanel", () => {
  it("idle state: shows the dropzone and calls onFileSelected for a valid image", () => {
    const onFileSelected = vi.fn();
    render(
      <UploadPanel
        isDemoMode={false}
        hasActiveAnalysis={false}
        state="idle"
        failure={null}
        uploadErrorMessage={null}
        onFileSelected={onFileSelected}
        onReset={noop}
      />,
    );

    const dropzone = screen.getByRole("button", {
      name: /upload a satellite or disaster image/i,
    });
    expect(dropzone).toBeInTheDocument();

    const file = new File(["x"], "aerial.png", { type: "image/png" });
    const input = dropzone.querySelector("input[type=file]") as HTMLInputElement;
    fireEvent.change(input, { target: { files: [file] } });

    expect(onFileSelected).toHaveBeenCalledWith(file);
  });

  it("rejects an unsupported file type before calling onFileSelected", () => {
    const onFileSelected = vi.fn();
    render(
      <UploadPanel
        isDemoMode={false}
        hasActiveAnalysis={false}
        state="idle"
        failure={null}
        uploadErrorMessage={null}
        onFileSelected={onFileSelected}
        onReset={noop}
      />,
    );

    const input = screen
      .getByRole("button", { name: /upload a satellite or disaster image/i })
      .querySelector("input[type=file]") as HTMLInputElement;
    const file = new File(["x"], "notes.txt", { type: "text/plain" });
    fireEvent.change(input, { target: { files: [file] } });

    expect(onFileSelected).not.toHaveBeenCalled();
    expect(screen.getByText(/unsupported file type/i)).toBeInTheDocument();
  });

  it("uploading state: shows the analysis-state indicator instead of the dropzone", () => {
    render(
      <UploadPanel
        isDemoMode={false}
        hasActiveAnalysis={true}
        state="uploading"
        failure={null}
        uploadErrorMessage={null}
        onFileSelected={noop}
        onReset={noop}
      />,
    );

    expect(screen.getByText("Uploading satellite imagery...")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /upload a satellite/i })).not.toBeInTheDocument();
  });

  it("surfaces an upload error without exposing raw error internals", () => {
    render(
      <UploadPanel
        isDemoMode={false}
        hasActiveAnalysis={false}
        state="idle"
        failure={null}
        uploadErrorMessage="413 Content Too Large"
        onFileSelected={noop}
        onReset={noop}
      />,
    );

    expect(screen.getByText("413 Content Too Large")).toBeInTheDocument();
  });

  it("demo mode: disables upload entirely", () => {
    render(
      <UploadPanel
        isDemoMode={true}
        hasActiveAnalysis={false}
        state="idle"
        failure={null}
        uploadErrorMessage={null}
        onFileSelected={noop}
        onReset={noop}
      />,
    );

    expect(screen.getByText(/demo mode is active/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /upload a satellite/i })).not.toBeInTheDocument();
  });
});
