// Offline o200k BPE counting. Vocabulary/pre-tokenization definition: OpenAI tiktoken,
// inspected in the locally installed VS Code Copilot tokenizer. No third-party code executed.
const fs = require('node:fs');
const path = require('node:path');
const bytes = fs.readFileSync(path.join(__dirname, 'assets/o200k_base.bin'));
const ranks = new Map();
for (let pos = 0; pos < bytes.length;) {
  let size = 0, shift = 0, b;
  do { b = bytes[pos++]; size += (b & 127) * 2 ** shift; shift += 7; } while (b & 128);
  if (pos + size > bytes.length || !size) throw Error('Invalid local vocabulary');
  ranks.set(bytes.subarray(pos, pos + size).toString('hex'), ranks.size); pos += size;
}
if (ranks.size !== 199998) throw Error('Unexpected vocabulary size');
const suffix = "(?:'[sStTmMdD]|'[rR][eE]|'[vV][eE]|'[lL][lL])?";
const pattern = new RegExp([
  String.raw`[^\r\n\p{L}\p{N}]?[\p{Lu}\p{Lt}\p{Lm}\p{Lo}\p{M}]*[\p{Ll}\p{Lm}\p{Lo}\p{M}]+` + suffix,
  String.raw`[^\r\n\p{L}\p{N}]?[\p{Lu}\p{Lt}\p{Lm}\p{Lo}\p{M}]+[\p{Ll}\p{Lm}\p{Lo}\p{M}]*` + suffix,
  String.raw`\p{N}{1,3}`, String.raw` ?[^\s\p{L}\p{N}]+[\r\n/]*`,
  String.raw`\s*[\r\n]+`, String.raw`\s+(?!\S)`, String.raw`\s+`
].join('|'), 'gu');
const cache = new Map();
let total = 0;
for (const match of fs.readFileSync(0, 'utf8').matchAll(pattern)) {
  const word = match[0];
  if (!cache.has(word)) {
    const data = Buffer.from(word, 'utf8');
    if (ranks.has(data.toString('hex'))) cache.set(word, 1);
    else {
      const parts = [...data].map(b => Buffer.from([b]));
      while (parts.length > 1) {
        let index = -1, best = Infinity;
        for (let i = 0; i < parts.length - 1; i++) {
          const rank = ranks.get(Buffer.concat([parts[i], parts[i+1]]).toString('hex'));
          if (rank !== undefined && rank < best) { best = rank; index = i; }
        }
        if (index < 0) break;
        parts.splice(index, 2, Buffer.concat([parts[index], parts[index+1]]));
      }
      cache.set(word, parts.length);
    }
  }
  total += cache.get(word);
}
process.stdout.write(JSON.stringify({input_tokens: total, encoding: 'o200k_base'}));
