import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { ActionButton } from "./ActionButton";
import { StatusBanner } from "./StatusBanner";
import { DemoGuidePanel, DEMO_STEPS } from "./DemoGuidePanel";
import { getPollingInterval, isRunInProgress } from "../hooks/usePolling";

describe("ActionButton", () => {
  it("renders children when not loading", () => {
    render(<ActionButton onClick={() => {}}>Submit</ActionButton>);
    expect(screen.getByText("Submit")).toBeTruthy();
  });

  it("shows spinner and disables when loading", () => {
    render(<ActionButton loading onClick={() => {}}>Submit</ActionButton>);
    expect(screen.getByText("Working…")).toBeTruthy();
    expect((screen.getByRole("button") as HTMLButtonElement).disabled).toBe(true);
  });

  it("calls onClick when clicked", () => {
    const fn = vi.fn();
    render(<ActionButton onClick={fn}>Go</ActionButton>);
    fireEvent.click(screen.getByText("Go"));
    expect(fn).toHaveBeenCalledOnce();
  });
});

describe("StatusBanner", () => {
  it("renders message", () => {
    render(<StatusBanner message="Success!" type="success" />);
    expect(screen.getByText("Success!")).toBeTruthy();
  });
});

describe("DemoGuidePanel", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("renders all demo steps", () => {
    render(<DemoGuidePanel />);
    expect(screen.getByText(/Demo Guide/)).toBeTruthy();
    DEMO_STEPS.forEach((step) => {
      expect(screen.getAllByText((content) => content.includes(step.title)).length).toBeGreaterThan(0);
    });
  });

  it("toggles step checkbox", () => {
    render(<DemoGuidePanel />);
    const checkbox = screen.getAllByRole("checkbox")[0];
    fireEvent.click(checkbox);
    expect((checkbox as HTMLInputElement).checked).toBe(true);
  });
});

describe("usePolling helpers", () => {
  it("detects in-progress runs", () => {
    expect(isRunInProgress("QUEUED")).toBe(true);
    expect(isRunInProgress("HANDED_OFF")).toBe(false);
  });

  it("returns adaptive intervals", () => {
    expect(getPollingInterval("QUEUED")).toBe(500);
    expect(getPollingInterval("HANDED_OFF")).toBe(3000);
    expect(getPollingInterval(undefined)).toBe(3000);
  });
});
