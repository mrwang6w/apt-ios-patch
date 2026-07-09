import { readFileSync, writeFileSync } from "node:fs";

const [output, ...inputs] = process.argv.slice(2);
if (!output || inputs.length !== 3) {
  throw new Error("usage: node make_deb.mjs OUTPUT debian-binary control.tar.gz data.tar.gz");
}

function field(value, width, label) {
  const text = String(value);
  if (Buffer.byteLength(text, "ascii") !== text.length || text.length > width) {
    throw new Error(`${label} does not fit in the ar header: ${text}`);
  }
  return text.padEnd(width, " ");
}

const expectedNames = ["debian-binary", "control.tar.gz", "data.tar.gz"];
const parts = [Buffer.from("!<arch>\n", "ascii")];
for (const [index, input] of inputs.entries()) {
  const data = readFileSync(input);
  const name = input.split("/").at(-1);
  if (name !== expectedNames[index]) throw new Error(`unexpected archive member: ${name}`);
  const header = `${field(name, 16, "name")}${field(0, 12, "mtime")}${field(0, 6, "uid")}${field(0, 6, "gid")}${field("100644", 8, "mode")}${field(data.length, 10, "size")}\x60\n`;
  parts.push(Buffer.from(header, "ascii"), data);
  if (data.length % 2) parts.push(Buffer.from("\n", "ascii"));
}

writeFileSync(output, Buffer.concat(parts));
