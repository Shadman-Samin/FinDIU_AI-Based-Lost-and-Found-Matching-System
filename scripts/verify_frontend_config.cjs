const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawnSync } = require('node:child_process');
const vm = require('node:vm');

const frontend = path.resolve(__dirname, '../frontend');
const build = path.join(frontend, 'build.cjs');
assert.ok(fs.existsSync(build), 'A production build must generate the configured HTTPS API URL');
const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'findiu-config-'));

try {
  fs.cpSync(frontend, directory, {
    recursive: true,
    filter: source => !source.split(path.sep).includes('dist'),
  });
  fs.writeFileSync(path.join(directory, '.env'), 'SECRET=must-not-be-published');
  const sourceConfig = fs.readFileSync(path.join(directory, 'js/config.js'), 'utf8');
  function run(apiURL) {
    return spawnSync(process.execPath, [build], {
      cwd: directory,
      env: { ...process.env, FINDIU_API_URL: apiURL, INTERNAL_TICK_TOKEN: 'must-not-be-published' },
      encoding: 'utf8',
    });
  }

  for (const value of ['', 'http://localhost:8000', 'https://localhost:8000',
    'http://api.example.com', 'https://user:password@api.example.com',
    'https://api.example.com/api/v1', 'https://api.example.com?token=x',
    'https://api.example.com#x', 'not-a-url']) {
    const result = run(value);
    assert.notEqual(result.status, 0, 'Missing or unsafe API URLs must fail the build');
    assert.match(result.stderr, /FINDIU_API_URL/);
  }

  const result = run('https://api.example.com/');
  assert.equal(result.status, 0, result.stderr);
  const output = path.join(directory, 'dist');
  const config = fs.readFileSync(path.join(output, 'js/config.js'), 'utf8');
  const context = { window: {} };
  vm.runInNewContext(config, context);
  assert.equal(context.window.FINDIU_CONFIG.apiBaseUrl, 'https://api.example.com');
  assert.ok(!config.includes('must-not-be-published'));
  for (const filename of ['index.html', 'auth.html', 'register.html', 'report.html',
    'dashboard.html', 'match.html', 'admin.html', 'style.css', 'favicon.svg']) {
    assert.ok(fs.existsSync(path.join(output, filename)), filename);
  }
  for (const filename of ['.env', 'build.cjs', 'verification.cjs', 'vercel.json']) {
    assert.equal(fs.existsSync(path.join(output, filename)), false, filename);
  }
  assert.equal(fs.readFileSync(path.join(directory, 'js/config.js'), 'utf8'), sourceConfig);
  const vercel = JSON.parse(fs.readFileSync(path.join(frontend, 'vercel.json'), 'utf8'));
  assert.equal(vercel.buildCommand, 'node build.cjs');
  assert.equal(vercel.outputDirectory, 'dist');
  console.log('PASS production API configuration, URL validation and public-only build');
} finally {
  fs.rmSync(directory, { recursive: true, force: true });
}
