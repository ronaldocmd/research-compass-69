"use client";

import { useState } from "react";

import { deleteResearchAction } from "@/lib/research-actions";

export function DeleteResearchButton({ id, title }: { id: string; title: string }) {
  const [confirming, setConfirming] = useState(false);

  if (!confirming) {
    return (
      <button type="button" className="btn danger" onClick={() => setConfirming(true)}>
        Excluir
      </button>
    );
  }

  return (
    <form action={deleteResearchAction} className="confirm">
      <input type="hidden" name="id" value={id} />
      <span>Excluir “{title}” definitivamente?</span>
      <button type="submit" className="btn danger">
        Sim, excluir
      </button>
      <button type="button" className="btn" onClick={() => setConfirming(false)}>
        Cancelar
      </button>
    </form>
  );
}
