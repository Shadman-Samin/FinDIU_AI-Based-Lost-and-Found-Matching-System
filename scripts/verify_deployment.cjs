const assert = require('node:assert/strict');
const crypto = require('node:crypto');

const frontend = new URL(process.env.FINDIU_FRONTEND_URL || 'https://findiu.vercel.app');
const createAccount = process.argv.includes('--create-test-account');
async function request(url, options = {}) {
  return fetch(url, { ...options, signal: AbortSignal.timeout(90000) });
}

(async () => {
  const configResponse = await request(new URL('/js/config.js', frontend));
  assert.equal(configResponse.status, 200, 'Public frontend configuration must be available');
  const config = await configResponse.text();
  const match = config.match(/["']?apiBaseUrl["']?\s*:\s*["']([^"']+)["']/);
  assert.ok(match, 'Public configuration must declare an API origin');
  const api = new URL(match[1]);
  assert.equal(api.protocol, 'https:', 'The deployed frontend must use a public HTTPS API, not localhost');
  assert.ok(api.hostname !== 'localhost' && !api.hostname.endsWith('.localhost') &&
    !/^127\./.test(api.hostname) && !['0.0.0.0', '[::]', '[::1]'].includes(api.hostname),
  'The deployed frontend must not target a loopback API');
  assert.equal((await request(new URL('/ready', api))).status, 200, 'API database must be ready');
  const metadata = await request(new URL('/api/v1/metadata', api));
  assert.equal(metadata.status, 200, 'Report metadata must be available');
  assert.ok((await metadata.json()).categories.length > 0);
  const cors = await request(new URL('/api/v1/auth/register', api), {
    method: 'OPTIONS',
    headers: {
      Origin: frontend.origin,
      'Access-Control-Request-Method': 'POST',
      'Access-Control-Request-Headers': 'content-type',
    },
  });
  assert.equal(cors.status, 200, 'Browser registration preflight must succeed');
  assert.equal(cors.headers.get('access-control-allow-origin'), frontend.origin);
  console.log('PASS deployed API configuration, database readiness, metadata and CORS');

  // Account creation is an explicit live write, never part of the default health check.
  if (createAccount) {
    const email = `synthetic-qa-${Date.now()}-${crypto.randomBytes(3).toString('hex')}@diu.edu.bd`;
    const password = crypto.randomBytes(24).toString('base64url');
    const register = await request(new URL('/api/v1/auth/register', api), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: 'Synthetic deployment QA', email, password, locale: 'en' }),
    });
    assert.equal(register.status, 201, 'Real account registration must persist successfully');
    const login = await request(new URL('/api/v1/auth/login', api), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    });
    assert.equal(login.status, 200, 'The newly registered account must be able to sign in');
    const token = (await login.json()).access_token;
    assert.ok(token);
    const reports = await request(new URL('/api/v1/items?mine=true', api), {
      headers: { Authorization: `Bearer ${token}` },
    });
    assert.equal(reports.status, 200, 'The account must have access to its own report board');
    assert.equal((await reports.json()).items.length, 0);
    console.log('PASS real synthetic account registration, login and authenticated report board');
  }
})().catch(error => {
  console.error(error.message);
  process.exitCode = 1;
});
