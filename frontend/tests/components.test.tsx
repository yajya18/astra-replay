import { describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { StageChecklist } from "@/components/job/stage-checklist";
import { StepCard } from "@/components/results/step-card";
import { ProcedurePanel } from "@/components/results/procedure-panel";
import { UnderTheHood } from "@/components/results/under-the-hood";
import { suggestedQueries } from "@/components/results/search-panel";
import { stepAt } from "@/components/results/results-view";
import { RESULT, job } from "./fixtures";

describe("StageChecklist", () => {
  it("marks completed, active and pending stages", () => {
    render(<StageChecklist job={job()} />);
    const list = screen.getByRole("list", { name: /processing stages/i });
    const items = within(list).getAllByRole("listitem");
    expect(items[0]).toHaveTextContent("Ingest");
    expect(items[0]).toHaveTextContent("100%");
    const active = items.find((li) => li.getAttribute("aria-current") === "step");
    expect(active).toHaveTextContent("Understanding actions");
    // understand: overall 0.4, completed weight 0.25, stage weight 0.45 -> 33%
    expect(active).toHaveTextContent("33%");
    expect(items[4]).toHaveTextContent("pending");
  });

  it("shows every stage as done when the job completed", () => {
    render(<StageChecklist job={job({ status: "completed", stage: "done", progress: 1 })} />);
    expect(screen.getAllByText("100%")).toHaveLength(9);
  });

  it("marks the failing stage", () => {
    render(<StageChecklist job={job({ status: "failed", stage: "understand" })} />);
    expect(screen.getByText(/failed,/)).toBeInTheDocument();
  });
});

describe("StepCard", () => {
  it("shows title, chips, time and alignment, and seeks on click", async () => {
    const onSelect = vi.fn();
    const onPlayClip = vi.fn();
    const step = RESULT.steps[1];
    render(
      <ul>
        <StepCard step={step} active={false} onSelect={onSelect} onPlayClip={onPlayClip} />
      </ul>,
    );
    expect(screen.getByText("Whisk the egg")).toBeInTheDocument();
    expect(screen.getByText("whisk")).toBeInTheDocument();
    expect(screen.getByText("fork")).toBeInTheDocument();
    expect(screen.getByText(/0:06–0:12/)).toBeInTheDocument();
    expect(screen.getByText("Done")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /keyframe/i })).toHaveAttribute(
      "src",
      expect.stringContaining("step_02.jpg"),
    );
    await userEvent.click(screen.getByRole("button", { name: /seek the video/i }));
    expect(onSelect).toHaveBeenCalledWith(step);
    await userEvent.click(screen.getByRole("button", { name: /play clip/i }));
    expect(onPlayClip).toHaveBeenCalledWith(step);
  });

  it("labels out-of-order steps", () => {
    render(
      <ul>
        <StepCard step={RESULT.steps[2]} active onSelect={() => {}} onPlayClip={() => {}} />
      </ul>,
    );
    expect(screen.getByText("Out of order")).toBeInTheDocument();
    expect(screen.getAllByRole("listitem")[0]).toHaveAttribute("aria-current", "step");
  });
});

describe("ProcedurePanel", () => {
  it("shows the verdict and each reference status, linked to steps", async () => {
    const onSelect = vi.fn();
    render(
      <ProcedurePanel alignment={RESULT.alignment!} steps={RESULT.steps} onSelect={onSelect} />,
    );
    expect(screen.getByTestId("verdict")).toHaveTextContent("3 of 4 steps completed");
    expect(screen.getByText("Missed")).toBeInTheDocument();
    expect(screen.getByText("Out of order")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /detected step 3/i }));
    expect(onSelect).toHaveBeenCalledWith(RESULT.steps[2]);
  });
});

describe("UnderTheHood", () => {
  it("lists providers and raw window actions", () => {
    render(<UnderTheHood result={RESULT} />);
    expect(screen.getByText("Under the hood")).toBeInTheDocument();
    expect(screen.getAllByText(/mock · mock-1/)).toHaveLength(2);
    const table = screen.getByRole("table");
    expect(within(table).getByText("Cracking the egg.")).toBeInTheDocument();
  });
});

describe("result helpers", () => {
  it("finds the active step for a time", () => {
    expect(stepAt(RESULT.steps, 0)).toBe(1);
    expect(stepAt(RESULT.steps, 7)).toBe(2);
    expect(stepAt(RESULT.steps, 13)).toBeNull();
    expect(stepAt(RESULT.steps, 17)).toBe(3);
  });

  it("suggests questions from detected actions", () => {
    const qs = suggestedQueries(RESULT);
    expect(qs[0]).toBe("When did I crack the egg?");
    expect(qs.length).toBe(3);
  });
});
