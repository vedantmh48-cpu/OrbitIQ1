/**
 * Tiny dependency-free Markdown → HTML renderer (safe subset).
 *
 * Supports the constructs the change-analysis and pipeline reports emit:
 * headings, paragraphs, bold/italic/inline-code/links, bullet & ordered
 * lists, tables, blockquotes and horizontal rules. All raw HTML is escaped
 * before any transformation, so user/LLM text can never inject markup.
 */
export function renderMarkdown(md) {
  if (!md) return "";
  const escaped = String(md)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");

  const blocks = splitBlocks(escaped);
  return blocks.map(renderBlock).join("\n");
}

function splitBlocks(text) {
  const blocks = [];
  let current = [];
  const lines = text.split("\n");
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    // Table: next line is a separator, current line contains pipes.
    if (
      isTableRow(line) &&
      i + 1 < lines.length &&
      /^\s*\|?[\s:|-]+\|?\s*$/.test(lines[i + 1]) &&
      lines[i + 1].includes("|")
    ) {
      flush();
      const header = line;
      const body = [];
      i += 2; // skip header + separator
      while (i < lines.length && isTableRow(lines[i])) {
        body.push(lines[i]);
        i++;
      }
      i--;
      blocks.push({ type: "table", header, body });
      continue;
    }
    if (line.trim() === "") {
      flush();
      continue;
    }
    current.push(line);
  }
  flush();
  return blocks;

  function flush() {
    if (!current.length) return;
    blocks.push(joinBlock(current));
    current = [];
  }
}

function isTableRow(line) {
  return line.includes("|") && line.trim().startsWith("|");
}

function joinBlock(lines) {
  const first = lines[0].trim();
  if (/^#{1,6}\s/.test(first)) {
    const level = first.match(/^(#{1,6})/)[1].length;
    return { type: "heading", level, text: first.replace(/^#{1,6}\s*/, "") };
  }
  if (lines.every(l => /^\s*[-*_]{3,}\s*$/.test(l.trim()))) {
    return { type: "hr" };
  }
  if (lines.every(l => /^\s*(?:>|&gt;)\s?/.test(l))) {
    return {
      type: "blockquote",
      text: lines.map(l => l.replace(/^\s*(?:>|&gt;)\s?/, "")).join(" ")
    };
  }
  if (lines.every(l => /^\s*[-*+]\s+/.test(l))) {
    return { type: "list", ordered: false, items: lines.map(l => l.replace(/^\s*[-*+]\s+/, "")) };
  }
  if (lines.every(l => /^\s*\d+[.)]\s+/.test(l))) {
    return { type: "list", ordered: true, items: lines.map(l => l.replace(/^\s*\d+[.)]\s+/, "")) };
  }
  return { type: "paragraph", text: lines.join(" ") };
}

function renderBlock(block) {
  switch (block.type) {
    case "heading":
      return `<h${block.level} class="md-h md-h-${block.level}">${inline(block.text)}</h${block.level}>`;
    case "hr":
      return `<hr class="md-hr" />`;
    case "blockquote":
      return `<blockquote class="md-quote">${inline(block.text)}</blockquote>`;
    case "list":
      const tag = block.ordered ? "ol" : "ul";
      const items = block.items.map(i => `<li>${inline(i)}</li>`).join("");
      return `<${tag} class="md-list">${items}</${tag}>`;
    case "table":
      return renderTable(block);
    default:
      return `<p class="md-p">${inline(block.text)}</p>`;
  }
}

function renderTable(block) {
  const cells = row => row.split("|").slice(1, -1).map(c => c.trim());
  const header = cells(block.header)
    .map(c => `<th>${inline(c)}</th>`)
    .join("");
  const rows = block.body
    .map(r => `<tr>${cells(r).map(c => `<td>${inline(c)}</td>`).join("")}</tr>`)
    .join("");
  return `<div class="md-table-wrap"><table class="md-table"><thead><tr>${header}</tr></thead><tbody>${rows}</tbody></table></div>`;
}

function inline(text) {
  return String(text)
    .replace(/`([^`]+)`/g, "<code class=\"md-code\">$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener" class="md-link">$1</a>')
    .replace(/\*([^*]+)\*/g, "<em>$1</em>");
}