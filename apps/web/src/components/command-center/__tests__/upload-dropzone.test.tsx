import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeAll, describe, expect, it, vi } from "vitest";

import { UploadDropzone } from "@/components/command-center/upload-dropzone";

// jsdom does not implement the Blob-URL APIs — stubbed here (not in the
// shared `vitest.setup.ts`) since this is currently the only component
// that touches them, matching the existing `window.matchMedia` stub's
// "polyfill only what's actually exercised" precedent.
beforeAll(() => {
  URL.createObjectURL = vi.fn(() => "blob:mock-preview-url");
  URL.revokeObjectURL = vi.fn();
});

const noop = () => {};

describe("UploadDropzone", () => {
  it("accepts a valid image via the file input and forwards it", () => {
    const onFileSelected = vi.fn();
    render(
      <UploadDropzone
        isUploading={false}
        uploadProgress={null}
        uploadErrorMessage={null}
        onFileSelected={onFileSelected}
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

  it("rejects an unsupported file type before calling onFileSelected", () => {
    const onFileSelected = vi.fn();
    render(
      <UploadDropzone
        isUploading={false}
        uploadProgress={null}
        uploadErrorMessage={null}
        onFileSelected={onFileSelected}
      />,
    );

    const input = screen
      .getByRole("button", { name: /upload a satellite or disaster image/i })
      .querySelector("input[type=file]") as HTMLInputElement;
    fireEvent.change(input, { target: { files: [new File(["x"], "notes.txt", { type: "text/plain" })] } });

    expect(onFileSelected).not.toHaveBeenCalled();
    expect(screen.getByText(/unsupported file type/i)).toBeInTheDocument();
  });

  it("shows a preview, filename, and size for a selected file (no dimensions until the image loads)", () => {
    render(
      <UploadDropzone isUploading={false} uploadProgress={null} uploadErrorMessage={null} onFileSelected={noop} />,
    );

    const input = screen
      .getByRole("button", { name: /upload a satellite or disaster image/i })
      .querySelector("input[type=file]") as HTMLInputElement;
    const file = new File(["x".repeat(2048)], "aerial.png", { type: "image/png" });
    fireEvent.change(input, { target: { files: [file] } });

    expect(screen.getByAltText("Preview of aerial.png")).toBeInTheDocument();
    expect(screen.getByText("aerial.png")).toBeInTheDocument();
    expect(screen.getByText(/2\.0 KB/)).toBeInTheDocument();
  });

  it("reports real dimensions once the preview image finishes loading", async () => {
    render(
      <UploadDropzone isUploading={false} uploadProgress={null} uploadErrorMessage={null} onFileSelected={noop} />,
    );

    const input = screen
      .getByRole("button", { name: /upload a satellite or disaster image/i })
      .querySelector("input[type=file]") as HTMLInputElement;
    fireEvent.change(input, {
      target: { files: [new File(["x"], "aerial.png", { type: "image/png" })] },
    });

    const img = screen.getByAltText("Preview of aerial.png") as HTMLImageElement;
    Object.defineProperty(img, "naturalWidth", { value: 800, configurable: true });
    Object.defineProperty(img, "naturalHeight", { value: 600, configurable: true });
    fireEvent.load(img);

    await waitFor(() => expect(screen.getByText(/800×600px/)).toBeInTheDocument());
  });

  it("shows real (not fabricated) progress while uploading, and an indeterminate bar before any progress event", () => {
    const { rerender } = render(
      <UploadDropzone isUploading={true} uploadProgress={null} uploadErrorMessage={null} onFileSelected={noop} />,
    );
    const bar = screen.getByRole("progressbar");
    expect(bar).not.toHaveAttribute("aria-valuenow");

    rerender(
      <UploadDropzone isUploading={true} uploadProgress={0.42} uploadErrorMessage={null} onFileSelected={noop} />,
    );
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "42");
  });

  it("shows an error with a retry action that re-sends the same file", () => {
    const onFileSelected = vi.fn();
    render(
      <UploadDropzone
        isUploading={false}
        uploadProgress={null}
        uploadErrorMessage="413 Content Too Large"
        onFileSelected={onFileSelected}
      />,
    );

    const input = screen
      .getByRole("button", { name: /upload a satellite or disaster image/i })
      .querySelector("input[type=file]") as HTMLInputElement;
    const file = new File(["x"], "aerial.png", { type: "image/png" });
    fireEvent.change(input, { target: { files: [file] } });
    onFileSelected.mockClear();

    expect(screen.getByText("413 Content Too Large")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /retry/i }));
    expect(onFileSelected).toHaveBeenCalledWith(file);
  });
});
