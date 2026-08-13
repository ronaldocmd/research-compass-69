import { defineTool } from "@lovable.dev/mcp-js";

import { listDocs } from "../docs";

export default defineTool({
  name: "list_rda_tickets",
  title: "List RDA tickets",
  description:
    "List the delivered Research Discovery Agent (RDA) Sprint 1 tickets with their documentation files.",
  inputSchema: {},
  annotations: { readOnlyHint: true, idempotentHint: true, openWorldHint: false },
  handler: () => {
    const items = listDocs().map(({ id, title, file }) => ({ id, title, file }));
    return {
      content: [
        {
          type: "text" as const,
          text: items.map((item) => `${item.id} — ${item.title} (${item.file})`).join("\n"),
        },
      ],
      structuredContent: { tickets: items },
    };
  },
});
