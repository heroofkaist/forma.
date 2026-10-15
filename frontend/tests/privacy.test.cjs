const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const Module = require('node:module');
const ts = require('typescript');
const React = require('react');
const { renderToStaticMarkup } = require('react-dom/server');

function load(file, imports = {}) {
  const filename = path.resolve(file), compiled = new Module(filename, module);
  compiled.paths = Module._nodeModulePaths(path.dirname(filename));
  const original = compiled.require.bind(compiled);
  compiled.require = (name) => imports[name] ?? original(name);
  compiled._compile(ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
  }).outputText, filename);
  return compiled.exports;
}

test('registration collects no identity or password before the neutral age screen', () => {
  const { AgeScreen } = load('src/components/age-screen.tsx', { '../lib/platform': {} });
  let index = 0;
  const hooks = { ...React, useEffect() {}, useState(initial) { return [index++ === 7 ? true : initial, () => {}]; } };
  const { AccountForm } = load('src/components/account-form.tsx', {
    react: hooks, 'next/link': { default: ({ children, href }) => React.createElement('a', { href }, children), __esModule: true },
    '../lib/platform': {}, './auth-provider': { useAuth: () => ({ user: null }) },
    './auth-study': { AuthStudy: () => null }, './forma-mark': { FormaMark: () => null }, './age-screen': { AgeScreen },
  });
  const html = renderToStaticMarkup(React.createElement(AccountForm, { mode: 'register' }));
  assert.match(html, /<select[^>]*required/);
  assert.match(html, /До 13 лет/);
  assert.match(html, /13–17 лет/);
  assert.match(html, /18 лет и старше/);
  assert.doesNotMatch(html, /<input|type="email"|type="password"/);
});

test('all authored font sources are local files with retained licenses', () => {
  const css = fs.readFileSync('src/app/fonts.css', 'utf8');
  const urls = [...css.matchAll(/url\(([^)]+)\)/g)].map((m) => m[1].replace(/['"]/g, ''));
  assert.ok(urls.length > 0);
  for (const url of urls) {
    assert.match(url, /^\/fonts\/[^/]+\.woff2$/);
    const data = fs.readFileSync('public' + url);
    assert.equal(data.subarray(0, 4).toString(), 'wOF2');
  }
  assert.ok(fs.readdirSync('public/fonts').some((name) => /OFL|LICENSE/.test(name)));
});

test('production browser policy blocks external font and recording destinations while preserving private previews', async () => {
  const { securityHeaders } = await import('../security-headers.mjs');
  const headers = Object.fromEntries(securityHeaders().map((h) => [h.key, h.value]));
  const csp = headers['Content-Security-Policy'];
  assert.match(csp, /(?:^|; )font-src 'self'(?:;|$)/);
  assert.match(csp, /(?:^|; )connect-src 'self'(?:;|$)/);
  assert.match(csp, /object-src 'self' blob:/);
  assert.match(csp, /frame-ancestors 'self'/);
  assert.doesNotMatch(csp, /unsafe-eval|https:|\*/);
  assert.match(securityHeaders(true).find((h) => h.key === 'Content-Security-Policy').value, /ws:/);
});

test('replay is absent from dependencies and the full application is marked private', () => {
  const pkg = JSON.parse(fs.readFileSync('package.json', 'utf8'));
  assert.doesNotMatch(JSON.stringify([pkg.dependencies, pkg.devDependencies]), /posthog|hotjar|fullstory|logrocket|rrweb|clarity|sentry/i);
  const layout = fs.readFileSync('src/app/layout.tsx', 'utf8');
  for (const marker of ['fs-exclude', 'ph-no-capture', 'rr-block', 'data-hj-suppress', 'data-private', 'data-clarity-mask']) assert.ok(layout.includes(marker));
});
