import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { ThemeToggle } from "@/components/theme-toggle";

describe("ThemeToggle", () => {
  it("switches the document theme and remembers it", async () => {
    document.documentElement.setAttribute("data-theme", "light");
    render(<ThemeToggle />);
    const button = screen.getByRole("button", { name: /switch to dark theme/i });
    await userEvent.click(button);
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
    expect(localStorage.getItem("theme")).toBe("dark");
    expect(await screen.findByRole("button", { name: /switch to light theme/i })).toBeVisible();
  });
});
