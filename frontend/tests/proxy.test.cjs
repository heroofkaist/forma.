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
  global.fetch = async (url, init) => { assert.equal(url.origin, 'https://backend.example'); assert.equal(init.redirect, 'manual'); return Response.json({ access_token: 'acct_secret', expires_in: 28800 }); };
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
test('budget status and authorized resume use the cookie proxy without AI credentials', async () => {
  const parts = ['api','document-analysis','synthetic-submission','resume'];
  let calls = 0;
  global.fetch = async (url, init) => {
    calls++;
    assert.equal(url.pathname, '/api/document-analysis/synthetic-submission/resume');
    assert.equal(init.headers.get('authorization'), 'Bearer acct_secret');
    assert.equal(init.method, 'POST');
    return Response.json({ detail: 'Paid allowance is not available; review manually.' }, { status: 409 });
  };
  const denied = await route.POST(request(parts, { method:'POST', origin:'https://attacker.example', cookie:'forma_session=acct_secret', body:'{}' }), context(parts));
  assert.equal(denied.status, 403); assert.equal(calls, 0);
  const paused = await route.POST(request(parts, { method:'POST', origin:'https://forma.example', cookie:'forma_session=acct_secret', body:'{}' }), context(parts));
  assert.equal(paused.status, 409); assert.equal(calls, 1);
  const statusParts = ['api','document-analysis','synthetic-submission','status'];
  global.fetch = async () => Response.json({ jobs:[{status:'awaiting_budget', error:'Manual review remains available.'}] });
  const status = await route.GET(request(statusParts, {cookie:'forma_session=acct_secret'}), context(statusParts));
  assert.equal((await status.json()).jobs[0].status, 'awaiting_budget');
  assert.equal(status.headers.get('cache-control'), 'no-store');
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

const apiFilename = path.resolve('src/lib/api.ts');
const apiModule = new Module(apiFilename, module);
apiModule.filename = apiFilename;
apiModule.paths = Module._nodeModulePaths(path.dirname(apiFilename));
const presentationFilename = path.resolve('src/lib/presentation.ts');
const presentationModule = new Module(presentationFilename, module);
presentationModule._compile(ts.transpileModule(fs.readFileSync(presentationFilename, 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText, presentationFilename);
apiModule.require = name => name === './presentation' ? presentationModule.exports : module.require(name);
apiModule._compile(ts.transpileModule(fs.readFileSync(apiFilename, 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText, apiFilename);
const { authenticatedResourceUrl, API_URL } = apiModule.exports;

test('PDF preview fetches private binary through proxy once using the session cookie', async () => {
  const previousWindow = global.window;
  const previousObjectUrl = URL.createObjectURL;
  const previousFetch = global.fetch;
  const pdf = Buffer.from('%PDF-1.7\nsynthetic multi-page PDF\n%%EOF');
  const browserPaths = [];
  const upstreamPaths = [];
  let blob;
  global.window = { location: { href: 'https://forma.example/teacher/submissions/synthetic-submission/review' }, sessionStorage: { getItem: () => null } };
  URL.createObjectURL = (value) => { blob = value; return 'blob:synthetic-preview'; };
  // Browser fetch -> actual proxy handler -> upstream fetch. No JS-readable
  // token exists: browser cookie is attached using credentials:same-origin.
  global.fetch = async (url, init) => {
    if (typeof url === 'string' && url.startsWith('/')) {
      browserPaths.push(url);
      assert.equal(init.credentials, 'same-origin');
      assert.equal(init.headers.get('authorization'), null);
      const requestedParts = url.slice('/api/backend/'.length).split('/');
      return route.GET(request(requestedParts, { cookie: 'forma_session=acct_teacher' }), context(requestedParts));
    }
    upstreamPaths.push(url.pathname);
    assert.equal(init.headers.get('authorization'), 'Bearer acct_teacher');
    assert.equal(init.redirect, 'manual');
    if (url.pathname !== '/api/submission-files/synthetic-submission') {
      return Response.json({ detail: 'This route has no access policy.' }, { status: 403 });
    }
    return new Response(pdf, { headers: { 'content-type': 'application/pdf', 'content-disposition': 'attachment; filename="submission.pdf"', 'cache-control': 'private, no-store' } });
  };
  try {
    for (const url of [`${API_URL}/api/submission-files/synthetic-submission`, '/api/submission-files/synthetic-submission']) {
      assert.equal(await authenticatedResourceUrl(url), 'blob:synthetic-preview');
      assert.equal(blob.type, 'application/pdf');
      assert.deepEqual(Buffer.from(await blob.arrayBuffer()), pdf);
    }
    assert.deepEqual(browserPaths, Array(2).fill('/api/backend/api/submission-files/synthetic-submission'));
    assert.deepEqual(upstreamPaths, Array(2).fill('/api/submission-files/synthetic-submission'));
  } finally {
    global.window = previousWindow; URL.createObjectURL = previousObjectUrl; global.fetch = previousFetch;
  }
});

test('proxy preserves a private PDF access denial without exposing file bytes', async () => {
  global.fetch = async (url, init) => {
    assert.equal(url.pathname, '/api/submission-files/synthetic-submission');
    assert.equal(init.headers.get('authorization'), 'Bearer acct_unrelated');
    return Response.json({ detail: 'Student account required.' }, { status: 403 });
  };
  const parts = ['api', 'submission-files', 'synthetic-submission'];
  const response = await route.GET(request(parts, { cookie: 'forma_session=acct_unrelated' }), context(parts));
  assert.equal(response.status, 403);
  assert.match(response.headers.get('cache-control'), /no-store/);
  assert.deepEqual(await response.json(), { detail: 'Student account required.' });
});

test('rubric approval and teacher assessment decisions retain same-origin cookie protection', async () => {
  for (const parts of [['api','assessment-rubrics','synthetic-assignment'], ['api','assessment','synthetic-submission','decisions']]) {
    let calls = 0;
    const body = JSON.stringify({ marker: 'synthetic-teacher-decision' });
    global.fetch = async (url, init) => {
      calls++;
      assert.equal(url.pathname, '/' + parts.join('/'));
      assert.equal(init.headers.get('authorization'), 'Bearer acct_secret');
      assert.equal(new TextDecoder().decode(init.body), body);
      return Response.json({ published: false }, { status: 201 });
    };
    const blocked = await route.POST(request(parts, { method:'POST', origin:'https://attacker.example', cookie:'forma_session=acct_secret', body }), context(parts));
    assert.equal(blocked.status, 403); assert.equal(calls, 0);
    const accepted = await route.POST(request(parts, { method:'POST', origin:'https://forma.example', cookie:'forma_session=acct_secret', body }), context(parts));
    assert.equal(accepted.status, 201); assert.equal((await accepted.json()).published, false);
  }
});

test('corrected age replaces the previous minor cookie and forwards the matching HttpOnly proof at signup',async()=>{
 const previous=process.env.NODE_ENV;process.env.NODE_ENV='production';
 const proof='v2.eligible.synthetic.signed';
 try{
  global.fetch=async(url,init)=>{assert.equal(init.headers.get('cookie'),'forma_age_screen=v2.guardian.previous.signed');assert.equal(new TextDecoder().decode(init.body),'{"age_band":"18_or_over"}');return Response.json({eligible:true,next_step:'account',age_check_token:proof});};
  const parts=['api','accounts','age-check'];
  const checked=await route.POST(request(parts,{method:'POST',origin:'https://forma.example',cookie:'forma_age_screen=v2.guardian.previous.signed',body:'{"age_band":"18_or_over"}'}),context(parts));
  assert.equal((await checked.json()).next_step,'account');
  assert.match(checked.headers.get('set-cookie'),/forma_age_screen=v2.eligible.synthetic.signed/);
  assert.match(checked.headers.get('set-cookie'),/HttpOnly/);assert.match(checked.headers.get('set-cookie'),/Secure/);
  global.fetch=async(url,init)=>{assert.equal(init.headers.get('cookie'),'forma_age_screen='+proof);return Response.json({message:'queued'},{status:202});};
  const register=['api','accounts','register'];
  const result=await route.POST(request(register,{method:'POST',origin:'https://forma.example',cookie:'forma_age_screen='+proof,body:JSON.stringify({age_check_token:proof})}),context(register));
  assert.equal(result.status,202);
 }finally{if(previous===undefined)delete process.env.NODE_ENV;else process.env.NODE_ENV=previous;}
});
