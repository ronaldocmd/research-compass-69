import { defineMcp } from "@lovable.dev/mcp-js";

import getProjectStackTool from "./tools/get-project-stack";
import getRdaDocTool from "./tools/get-rda-doc";
import getRunInstructionsTool from "./tools/get-run-instructions";
import listRdaTicketsTool from "./tools/list-rda-tickets";

export default defineMcp({
  name: "research-foundation",
  title: "Research Foundation",
  version: "0.1.0",
  instructions:
    "Read-only tools describing the Research Discovery Agent (RDA) Sprint 1 foundation. Use `get_project_stack` for the architecture, `list_rda_tickets` and `get_rda_doc` for delivered ticket documentation, and `get_run_instructions` for local Docker Compose commands and URLs.",
  tools: [getProjectStackTool, listRdaTicketsTool, getRdaDocTool, getRunInstructionsTool],
});
