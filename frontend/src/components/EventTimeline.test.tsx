import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { EventTimeline } from "./EventTimeline";

describe("EventTimeline", () => {
  it("renders events", () => {
    render(
      <EventTimeline
        events={[
          {
            event_id: "E1",
            run_id: "R1",
            timestamp: new Date().toISOString(),
            stage: "INGRESS",
            component: "ingress",
            action: "request_received",
            status: "SUCCESS",
            message: "ok",
          },
        ]}
      />
    );
    expect(screen.getByText(/request received/i)).toBeTruthy();
  });

  it("shows empty state", () => {
    render(<EventTimeline events={[]} />);
    expect(screen.getByText(/no events yet/i)).toBeTruthy();
  });
});
