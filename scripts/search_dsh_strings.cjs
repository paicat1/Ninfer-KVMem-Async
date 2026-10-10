// search_dsh_strings.cjs — byte-level needle search inside a binary (exe/asar).
// Usage: node search_dsh_strings.cjs <file> <needle1> [needle2 ...]
// Prints per needle: hit count, first offsets (up to 5), and 160-byte context of first hit.
'use strict';
const fs = require('fs');

function printable(s) {
  return s.replace(/[^\x20-\x7E]/g, (c) => {
    const b = c.charCodeAt(0);
    return b >= 0x20 && b <= 0x7E ? c : b === 0 ? '\\0' : '.';
  });
}

const [file, ...needles] = process.argv.slice(2);
if (!file || needles.length === 0) {
  console.error('usage: node search_dsh_strings.cjs <file> <needle...>');
  process.exit(2);
}
const buf = fs.readFileSync(file);
console.log(`file=${file} bytes=${buf.length}`);

for (const needle of needles) {
  const pat = Buffer.from(needle, 'utf8');
  const hits = [];
  let i = buf.indexOf(pat);
  while (i !== -1 && hits.length < 2000) {
    hits.push(i);
    i = buf.indexOf(pat, i + 1);
  }
  console.log(`\n=== ${needle} ===  hits=${hits.length}`);
  if (hits.length) {
    console.log('offsets: ' + hits.slice(0, 5).join(', '));
    const o = hits[0];
    const from = Math.max(0, o - 80);
    const ctx = buf.subarray(from, Math.min(buf.length, o + pat.length + 80));
    console.log('ctx@' + o + ': ' + printable(ctx.toString('latin1')));
  }
}
