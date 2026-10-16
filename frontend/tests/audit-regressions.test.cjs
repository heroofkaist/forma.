const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const Module = require('node:module');
const ts = require('typescript');
const React = require('react');
const { renderToStaticMarkup } = require('react-dom/server');

function load(source, imports = {}) {
  const filename = path.resolve(source);
  const compiled = new Module(filename, module);
  compiled.filename = filename;
  compiled.paths = Module._nodeModulePaths(path.dirname(filename));
  const original = compiled.require.bind(compiled);
  compiled.require = (name) => imports[name] ?? original(name);
  compiled._compile(ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
  }).outputText, filename);
  return compiled.exports;
}
const results = load('src/lib/published-result.ts');
const { PublishedResult } = load('src/components/published-result.tsx', { '../lib/published-result': results });
const { reviewPath } = load('src/lib/review-navigation.ts');
const { studentProcessingMessage, teacherProcessingMessage } = load('src/lib/presentation.ts');

test('published feedback renders frozen names, bounds, zero and readable historical fallback', () => {
  const grade = { id: 'g', points: 0, maximum_score: 10, published_at: '2026-10-15T00:00:00Z',
    feedback: 'Teacher <script>feedback</script>', criteria: [
      { question_id: 'q1', criterion_id: 'q1-overall', description: 'Обоснование решения', points: 0, maximum_points: 5, comment: 'Human words' },
      { question_id: 'q2', criterion_id: 'q2-overall', description: 'q2-overall', points: 0, comment: 'Historical words' },
    ] };
  const html = renderToStaticMarkup(React.createElement(PublishedResult, { grade }));
  assert.match(html, /Результат опубликован/);
  assert.match(html, /0 \/ 10/);
  assert.match(html, /Обоснование решения/);
  assert.match(html, /0 \/ 5/);
  assert.match(html, /Критерий 2/);
  assert.match(html, /Historical words/);
  assert.doesNotMatch(html, /q1-overall|q2-overall|<script>/);
  assert.match(html, /&lt;script&gt;/);
});

test('published human result takes precedence over every AI state', () => {
  for (const status of ['failed', 'awaiting_budget', 'queued', 'completed', 'needs_review']) {
    assert.equal(studentProcessingMessage(status, true), 'Результат опубликован');
  }
  assert.match(studentProcessingMessage('completed'), /ожидает проверки преподавателя/);
  assert.match(teacherProcessingMessage('failed', true), /Можно проверить вручную/);
  assert.doesNotMatch(teacherProcessingMessage('failed', true), /provider|timeout|Exception/);
});

test('academic links resolve to one review destination while independent scan workflows remain available', () => {
  assert.equal(reviewPath({ id: 'legacy', academic_assignment_id: 'academic' }), '/teacher/assignments/academic/submissions');
  assert.equal(reviewPath({ id: 'scan', academic_assignment_id: null }), '/assignments/scan/review');
});

test('development previews return a real production 404 before response streaming begins', () => {
  const { middleware, config } = load('src/middleware.ts');
  assert.deepEqual(config.matcher, ['/design-preview/:path*', '/teacher/review-preview/:path*']);
  const previous = process.env.NODE_ENV;
  try {
    process.env.NODE_ENV = 'production';
    const response = middleware();
    assert.equal(response.status, 404);
    assert.equal(response.headers.get('cache-control'), 'private, no-store');
    process.env.NODE_ENV = 'development';
    assert.equal(middleware().headers.get('x-middleware-next'), '1');
  } finally {
    if (previous === undefined) delete process.env.NODE_ENV;
    else process.env.NODE_ENV = previous;
  }
});
