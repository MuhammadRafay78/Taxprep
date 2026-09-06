/**
 * Reconstructs pdfplumber-style "rows" of text from a PDF using unpdf
 * (a serverless-friendly PDF.js build made for edge runtimes like Cloudflare
 * Workers). PDF.js gives us individual text runs with x/y positions rather
 * than pre-assembled lines, so we group runs that share a y-coordinate
 * (allowing a little jitter) into a row and sort left-to-right within it —
 * the same "row of label ... amount" shape our line-matching logic expects.
 */
import { extractTextItems, type StructuredTextItem } from "unpdf";

const ROW_TOLERANCE = 2.5;

function groupIntoRows(items: StructuredTextItem[]): string[] {
  const filtered = items.filter((it) => it.str.trim().length > 0);
  // Top of page first (higher y), then left to right within a row.
  const sorted = [...filtered].sort((a, b) => b.y - a.y || a.x - b.x);

  const rows: { y: number; items: StructuredTextItem[] }[] = [];
  for (const item of sorted) {
    const row = rows.find((r) => Math.abs(r.y - item.y) <= ROW_TOLERANCE);
    if (row) {
      row.items.push(item);
    } else {
      rows.push({ y: item.y, items: [item] });
    }
  }

  return rows
    .map((row) =>
      row.items
        .sort((a, b) => a.x - b.x)
        .map((it) => it.str)
        .join(" ")
        .replace(/\s+/g, " ")
        .trim(),
    )
    .filter((row) => row.length > 0);
}

/** Returns one array of row-strings per PDF page, top-to-bottom. */
export async function extractPdfPages(bytes: Uint8Array): Promise<string[][]> {
  const { items } = await extractTextItems(bytes);
  return items.map(groupIntoRows);
}
