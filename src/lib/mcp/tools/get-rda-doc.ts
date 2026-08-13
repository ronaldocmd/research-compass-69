import { defineTool, ToolError } from "@lovable.dev/mcp-js";
import { z } from "zod";

import { findDoc, listDocs } from "../docs";

export default defineTool({
  name: "get_rda_doc",
  title: "Get RDA ticket documentation",
  description:
    "Return the full markdown documentation for one RDA ticket, e.g. 'RDA-004' or 'RDA-005-research-model'.",
  inputSchema: {
    ticket: z.string().min(1).describe("Ticket id or documentation file name, e.g. RDA-004."),
  },
  outputSchema: {
    id: z.string(),
    title: z.string(),
    file: z.string(),
  },
  annotations: { readOnlyHint: true, idempotentHint: true, openWorldHint: false },
  handler: ({ ticket }) => {
    const doc = findDoc(ticket);
    if (!doc) {
      const known = listDocs()
        .map((item) => item.id)
        .join(", ");
      throw new ToolError(`No documentation found for "${ticket}". Available tickets: ${known}.`);
    }
    return {
      content: [{ type: "text" as const, text: doc.content }],
      structuredContent: { id: doc.id, title: doc.title, file: doc.file },
    };
  },
});
