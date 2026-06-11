type ParsedRecord = {
  name: string;
  description?: string;
};

function splitCsvLine(line: string): string[] {
  const fields: string[] = [];
  let cur = "";
  let inQuotes = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (inQuotes) {
      if (ch === '"') {
        if (line[i + 1] === '"') {
          cur += '"';
          i++;
        } else {
          inQuotes = false;
        }
      } else {
        cur += ch;
      }
    } else if (ch === '"') {
      inQuotes = true;
    } else if (ch === ",") {
      fields.push(cur);
      cur = "";
    } else {
      cur += ch;
    }
  }
  fields.push(cur);
  return fields;
}

export function parseContactsCsv(csv: string): ParsedRecord[] {
  const lines = csv.replace(/\r\n/g, "\n").replace(/\r/g, "\n").split("\n");
  const records: ParsedRecord[] = [];
  let headerCols: string[] | null = null;

  for (const rawLine of lines) {
    const line = rawLine.trim();
    if (line === "") continue;
    const fields = splitCsvLine(line);
    if (headerCols === null) {
      headerCols = fields.map((f) => f.trim().toLowerCase());
      continue;
    }
    const row: Record<string, string> = {};
    headerCols.forEach((col, idx) => {
      row[col] = (fields[idx] ?? "").trim();
    });
    const name = row.name ?? row.姓名 ?? fields[0] ?? "";
    if (name === "") continue;
    records.push({
      name,
      description: row.description ?? row.备注 ?? undefined,
    });
  }
  return records;
}
