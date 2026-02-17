#!/usr/bin/env node
/**
 * Merges license data from cargo-about (Rust), pnpm licenses (JS),
 * and pip-licenses (Python) into a Credits.html for the macOS About panel.
 *
 * Layout: alphabetical package index with anchor links at the top,
 * followed by each package's full license text.
 *
 * Usage: node scripts/merge-licenses.mjs <rust.json> <js.json> <python.json> <output.html>
 */

import { readFileSync, writeFileSync } from "fs";

const [rustPath, jsPath, pyPath, outPath] = process.argv.slice(2);
if (!rustPath || !jsPath || !pyPath || !outPath) {
  console.error(
    "Usage: node scripts/merge-licenses.mjs <rust.json> <js.json> <python.json> <output.html>"
  );
  process.exit(1);
}

function readJSON(path) {
  return JSON.parse(readFileSync(path, "utf-8"));
}

function esc(str) {
  return str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function nameHtml(entry) {
  return entry.url
    ? `<a href="${esc(entry.url)}">${esc(entry.name)}</a>`
    : esc(entry.name);
}

// --- Rust (cargo-about --format json) ---
function parseRust(data) {
  const entries = [];
  for (const license of data.licenses ?? []) {
    for (const usage of license.used_by ?? []) {
      const crate = usage.crate;
      entries.push({
        name: crate.name,
        version: crate.version,
        license: license.id,
        url: crate.source?.startsWith("registry+")
          ? `https://crates.io/crates/${crate.name}`
          : undefined,
        licenseText: license.text || undefined,
      });
    }
  }
  const seen = new Map();
  for (const entry of entries) {
    const key = `${entry.name}@${entry.version}`;
    if (!seen.has(key)) {
      seen.set(key, entry);
    }
  }
  return [...seen.values()];
}

// --- JavaScript (pnpm licenses list --json) ---
function parseJS(data) {
  const entries = [];
  for (const packages of Object.values(data)) {
    for (const pkg of packages) {
      entries.push({
        name: pkg.name,
        version: pkg.versions?.[0] ?? "",
        license: pkg.license ?? "UNKNOWN",
        url: pkg.homepage || undefined,
        licenseText: pkg.licenseText || undefined,
      });
    }
  }
  return entries;
}

// --- Python (pip-licenses --format=json --with-license-file --no-license-path --with-urls) ---
function parsePython(data) {
  return data
    .filter((pkg) => pkg.Name !== "local-translate")
    .map((pkg) => ({
      name: pkg.Name,
      version: pkg.Version,
      license: pkg.License ?? "UNKNOWN",
      url: pkg.URL && pkg.URL !== "UNKNOWN" ? pkg.URL : undefined,
      licenseText:
        pkg.LicenseText && pkg.LicenseText !== "UNKNOWN"
          ? pkg.LicenseText
          : undefined,
    }));
}

function render(allEntries) {
  const sorted = allEntries.sort((a, b) =>
    a.name.toLowerCase().localeCompare(b.name.toLowerCase())
  );

  // Index
  let index = "";
  for (let i = 0; i < sorted.length; i++) {
    const p = sorted[i];
    index += `<div class="idx">${nameHtml(p)}\u00a0<span class="ver">${esc(p.version)}</span> <a class="lic-link" href="#lic-${i}">${esc(p.license)}</a></div>\n`;
  }

  // License texts
  let texts = "";
  for (let i = 0; i < sorted.length; i++) {
    const p = sorted[i];
    if (!p.licenseText) continue;
    texts += `<h3 id="lic-${i}">${nameHtml(p)}\u00a0${esc(p.version)}</h3>\n`;
    texts += `<pre>${esc(p.licenseText)}</pre>\n`;
  }

  return `<div class="index">\n${index}</div>\n<hr>\n${texts}`;
}

const rust = parseRust(readJSON(rustPath));
const js = parseJS(readJSON(jsPath));
const python = parsePython(readJSON(pyPath));
const all = [...rust, ...js, ...python];

const html = `<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body {
    font-family: -apple-system, BlinkMacSystemFont, sans-serif;
    font-size: 10px;
    color: #333;
    padding: 4px 6px;
    line-height: 1.4;
  }
  @media (prefers-color-scheme: dark) {
    body { color: #ccc; }
    a { color: #6ea8fe; }
    pre { background: rgba(255,255,255,0.05); }
  }
  .idx { padding: 1px 0; }
  .ver { color: #888; }
  .lic-link { color: #888; font-size: 9px; }
  hr {
    border: none;
    border-top: 1px solid rgba(128,128,128,0.3);
    margin: 12px 0;
  }
  h3 {
    font-size: 10px;
    font-weight: 600;
    margin: 14px 0 2px 0;
  }
  pre {
    font-family: ui-monospace, Menlo, monospace;
    font-size: 8.5px;
    line-height: 1.4;
    white-space: pre-wrap;
    word-break: break-word;
    background: rgba(128,128,128,0.08);
    padding: 6px;
    border-radius: 4px;
    margin: 2px 0 0 0;
  }
  a { color: #0066cc; text-decoration: none; }
</style>
</head>
<body>
<p>This application incorporates ${all.length} open source packages.</p>
${render(all)}
</body>
</html>
`;

writeFileSync(outPath, html);
console.log(`Generated Credits.html: ${all.length} packages → ${outPath}`);
