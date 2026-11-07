// Trusted fixture helper. The reviewed CI script verifies this file against
// the base commit before any untrusted worker source can be evaluated.
import vm from 'node:vm';
import { readFileSync } from 'node:fs';

export async function loadApprovedSource(relativePath) {
  if (typeof relativePath !== 'string' || !/^\.\.\/src\/[a-z0-9-]+\.mjs$/.test(relativePath)) {
    throw new TypeError('Expected one approved synthetic src module');
  }
  const url = new URL(relativePath, import.meta.url);
  if (url.protocol !== 'file:' || !url.pathname.includes('/src/')) {
    throw new Error('Invalid source URL');
  }
  const code = readFileSync(url, 'utf8');
  const context = vm.createContext(Object.create(null), {
    codeGeneration: { strings: false, wasm: false },
  });
  const module = new vm.SourceTextModule(code, {
    context,
    identifier: url.href,
  });
  await module.link(() => { throw new Error('Worker source imports are forbidden'); });
  await module.evaluate({ timeout: 1000 });
  return module.namespace;
}
