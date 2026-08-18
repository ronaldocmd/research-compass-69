import React from "react";
import { describe, expect, it, vi, afterEach } from "vitest";
import { render, screen, fireEvent, cleanup } from "@testing-library/react";

import { DeleteResearchButton } from "@/components/DeleteResearchButton";

describe("RDA-010 DeleteResearchButton", () => {
  afterEach(() => {
    cleanup();
  });

  it("renders the delete button initially", () => {
    render(<DeleteResearchButton id="research-123" title="Minha Pesquisa" />);

    expect(screen.getByRole("button", { name: "Excluir" })).toBeInTheDocument();
    expect(screen.queryByText(/Excluir "Minha Pesquisa" definitivamente/)).not.toBeInTheDocument();
  });

  it("shows confirmation after clicking delete", () => {
    render(<DeleteResearchButton id="research-123" title="Minha Pesquisa" />);

    fireEvent.click(screen.getByRole("button", { name: "Excluir" }));

    expect(screen.getByText(/Excluir.*Minha Pesquisa.*definitivamente/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sim, excluir" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Cancelar" })).toBeInTheDocument();
  });

  it("hides confirmation after clicking cancel", () => {
    render(<DeleteResearchButton id="research-123" title="Minha Pesquisa" />);

    fireEvent.click(screen.getByRole("button", { name: "Excluir" }));
    fireEvent.click(screen.getByRole("button", { name: "Cancelar" }));

    expect(screen.getByRole("button", { name: "Excluir" })).toBeInTheDocument();
    expect(screen.queryByText(/Excluir "Minha Pesquisa" definitivamente/)).not.toBeInTheDocument();
  });
});
