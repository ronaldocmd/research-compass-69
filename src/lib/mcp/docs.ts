/**
 * Bundled RDA documentation (docs/RDA-*.md), inlined at build time so the
 * Worker never needs filesystem access at runtime.
 */
const modules = import.meta.glob("../../../docs/*.md", {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>;

export type RdaDoc = {
  id: string;
  title: string;
  file: string;
  content: string;
};

function toDoc(path: string, content: string): RdaDoc {
  const file = path.split("/").pop() ?? path;
  const id = file.replace(/\.md$/i, "");
  const heading = content.split("\n").find((line) => line.startsWith("# "));
  return {
    id,
    title: heading ? heading.replace(/^#\s*/, "").trim() : id,
    file: `docs/${file}`,
    content,
  };
}

export function listDocs(): RdaDoc[] {
  return Object.entries(modules)
    .map(([path, content]) => toDoc(path, content))
    .sort((a, b) => a.id.localeCompare(b.id));
}

export function findDoc(id: string): RdaDoc | undefined {
  const needle = id.trim().toLowerCase().replace(/\.md$/i, "");
  const docs = listDocs();
  return (
    docs.find((doc) => doc.id.toLowerCase() === needle) ??
    docs.find((doc) => doc.id.toLowerCase().startsWith(needle)) ??
    docs.find((doc) => doc.id.toLowerCase().includes(needle))
  );
}
