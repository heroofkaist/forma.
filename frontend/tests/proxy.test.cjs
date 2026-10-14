const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const Module = require('node:module');
const ts = require('typescript');
const { NextRequest } = require('next/server');
const filename = path.resolve('src/app/api/backend/[...path]/route.ts');
const compiled = ts.transpileModule(fs.readFileSync(filename, 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText;
const routeModule = new Module(filename, module);
routeModule.filename = filename;
routeModule.paths = Module._nodeModulePaths(path.dirname(filename));
// Cloudflare context is absent in ordinary Node, as in next start.
const originalRequire = routeModule.require.bind(routeModule);
routeModule.require = (name) => name === '@opennextjs/cloudflare' ? { getCloudflareContext() { throw new Error('No Worker context'); } } : originalRequire(name);
routeModule._compile(compiled, filename);
const route = routeModule.exports;
process.env.FORMA_BACKEND_URL = 'https://backend.example';
function request(parts, { method = 'GET', origin, cookie, body, headers = {} } = {}) {
  const values = { ...headers };
  if (origin) values.origin = origin;
  if (cookie) values.cookie = cookie;
  return new NextRequest(`https://forma.example/api/backend/${parts.join('/')}`, { method, headers: values, ...(body ? { body } : {}) });
}
function context(path) { return { params: Promise.resolve({ path }) }; }

test('mutations require exact same-origin Origin before contacting backend', async () => {
  let calls = 0; global.fetch = async () => { calls++; throw new Error(); };
  for (const origin of [undefined, 'https://attacker.example']) {
    const response = await route.POST(request(['api','auth','login'], { method: 'POST', origin, body: '{}' }), context(['api','auth','login']));
    assert.equal(response.status, 403);
  }
  assert.equal(calls, 0);
});
test('login strips bearer token from response and uses HttpOnly cookie', async () => {
  global.fetch = async (url, init) => { assert.equal(url.origin, 'https://backend.example'); assert.equal(init.redirect, 'error'); return Response.json({ access_token: 'acct_secret', expires_in: 28800 }); };
  const response = await route.POST(request(['api','auth','login'], { method: 'POST', origin: 'https://forma.example', body: '{}' }), context(['api','auth','login']));
  assert.deepEqual(await response.json(), { authenticated: true });
  const cookie = response.headers.get('set-cookie');
  assert.match(cookie, /HttpOnly/i); assert.match(cookie, /SameSite=lax/i); assert.match(cookie, /forma_session=acct_secret/);
});
test('cookie authorizes private document and logout revokes account backend session', async () => {
  global.fetch = async (url, init) => { assert.equal(init.headers.get('authorization'), 'Bearer acct_secret'); return Response.json({ ok: true }); };
  assert.equal((await route.GET(request(['academic','courses'], { cookie: 'forma_session=acct_secret' }), context(['academic','courses']))).status, 200);
  global.fetch = async (url, init) => { assert.equal(url.pathname, '/api/accounts/logout'); return Response.json({ message: 'signed out' }); };
  const response = await route.POST(request(['api','auth','logout'], { method: 'POST', origin: 'https://forma.example', cookie: 'forma_session=acct_secret' }), context(['api','auth','logout']));
  assert.match(response.headers.get('set-cookie'), /Max-Age=0/);
});
test('rejects traversal and arbitrary proxy paths without fetching', async () => {
  let calls = 0; global.fetch = async () => { calls++; throw new Error(); };
  for (const parts of [['api','..','secret'], ['https:','attacker.example'], ['api','bad\\path']]) {
    assert.equal((await route.GET(request(['api','placeholder']), context(parts))).status, 400);
  }
  assert.equal(calls, 0);
});
test('oversized upload rejected and backend outages reported accurately', async () => {
  global.fetch = async () => { throw new Error('offline'); };
  assert.equal((await route.POST(request(['api','upload'], { method: 'POST', origin: 'https://forma.example', headers: { 'content-length': String(33*1024*1024) } }), context(['api','upload']))).status, 413);
  assert.equal((await route.GET(request(['api','health']), context(['api','health']))).status, 502);
});
