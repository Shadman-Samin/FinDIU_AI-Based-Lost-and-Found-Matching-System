const fs = require('node:fs');

let api;
try {
  api = new URL(process.env.FINDIU_API_URL || '');
} catch {
  throw new Error('FINDIU_API_URL must be the public HTTPS origin of the deployed API');
}
if (api.protocol !== 'https:' || api.username || api.password || api.search || api.hash ||
    api.pathname !== '/' || api.hostname === 'localhost' || api.hostname.endsWith('.localhost') ||
    /^127\./.test(api.hostname) || ['0.0.0.0', '[::]', '[::1]'].includes(api.hostname)) {
  throw new Error('FINDIU_API_URL must be a public HTTPS origin without credentials, path or query');
}

fs.rmSync('dist', { recursive: true, force: true });
fs.mkdirSync('dist/js', { recursive: true });
for (const filename of ['index.html', 'auth.html', 'register.html', 'report.html',
  'dashboard.html', 'match.html', 'admin.html', 'style.css', 'favicon.svg']) {
  fs.copyFileSync(filename, `dist/${filename}`);
}
for (const filename of fs.readdirSync('js').filter(name => name.endsWith('.js'))) {
  fs.copyFileSync(`js/${filename}`, `dist/js/${filename}`);
}
fs.writeFileSync('dist/js/config.js',
  `window.FINDIU_CONFIG = ${JSON.stringify({ apiBaseUrl: api.origin })};\n`);
console.log('Built the frontend with a validated production API origin');
