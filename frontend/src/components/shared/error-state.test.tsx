import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { ErrorState } from "./error-state";

describe("ErrorState Component", () => {
  it("renders the error message", () => {
    render(<ErrorState message="Test error occurred" />);
    
    expect(screen.getByText("Test error occurred")).toBeInTheDocument();
  });

  it("renders the retry button when onRetry is provided", () => {
    const onRetryMock = vi.fn();
    render(<ErrorState message="Another error" onRetry={onRetryMock} />);
    
    expect(screen.getByRole("button", { name: /retry/i })).toBeInTheDocument();
  });
});
