// Run with Playwright available to Node. Components do not write application data.
const assert = require('node:assert/strict');
const { firefox } = require('playwright');

const base = process.env.FINDIU_FRONTEND_URL || 'http://localhost:5500';
const match = {
  score: 1, text_sim: 1, image_sim: 1, attr_score: 1, threshold: 0.75,
  scoring_version: '2.0-local-hybrid',
  evidence: {
    mode: 'local', weights: { text: 0.45, image: 0.25, attributes: 0.3 },
    text: { local: 1, semantic: null, weights: { local: 1, semantic: 0 }, lexical: {
      score: 1, jaccard: 1, char_dice: 1, containment: 1,
      weights: { jaccard: 0.45, char_dice: 0.35, containment: 0.2 },
      shared_terms: ['blue', 'zipper', '<img src=x onerror=alert(1)>']
    } },
    image: { local: 1, semantic: null, weights: { local: 1, semantic: 0 }, perceptual: {
      score: 1, dhash_sim: 1, ahash_sim: 1, histogram_sim: 1,
      dhash_distance: 0, ahash_distance: 0, weights: { dhash: 0.45, ahash: 0.2, histogram: 0.35 }
    } },
    attributes: { color: 1, brand: 1, location: 1, date: 1, date_gap_days: 0,
      weights: { color: 0.4, brand: 0.3, location: 0.2, date: 0.1 } }
  }
};

(async () => {
  const browser = await firefox.launch({ headless: true });
  const failures = [];
  try {
    const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
    await page.goto(`${base}/index.html`);
    await page.evaluate(() => localStorage.setItem('findiu_locale', 'en'));
    await page.reload();
    for (const mode of ['local', 'hybrid', 'historical']) {
      try {
        const input = JSON.parse(JSON.stringify(match));
        if (mode === 'hybrid') {
          input.evidence.mode = 'hybrid';
          input.evidence.text.semantic = 0.8;
          input.evidence.text.weights = { local: 0.65, semantic: 0.35 };
          input.text_sim = 0.93; input.score = 0.9685;
        } else if (mode === 'historical') {
          input.evidence = null; input.threshold = null; input.scoring_version = '1.0';
        }
        await page.evaluate(input => document.querySelector('#main').replaceChildren(FinDIUSession.evidence(input)), input);
        await page.getByText({ local: 'Local matching', hybrid: 'Local + semantic', historical: 'Historical score' }[mode], { exact: true }).waitFor({ timeout: 4000 });
        if (mode !== 'historical') {
          await page.getByText('Detailed signals', { exact: true }).click();
          await page.getByText('Token overlap (Jaccard)').waitFor({ timeout: 4000 });
          assert.equal(await page.locator('.evidence img').count(), 0, 'Shared clues must be text, never HTML');
          if (mode === 'hybrid') {
            await page.getByText('Semantic text similarity').waitFor();
            assert.ok(await page.getByText('80%', { exact: true }).count());
          }
        } else {
          assert.equal(await page.getByText('Detailed signals', { exact: true }).count(), 0);
          assert.equal(await page.evaluate(() => FinDIUSession.threshold(null)), 'Not recorded');
        }
        assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false, 'Evidence must fit the mobile viewport');
        console.log(`PASS ${mode} evidence`);
      } catch (error) {
        failures.push(`${mode}: ${error.message}`);
      }
    }
    assert.deepEqual(failures, []);
    await page.route('**/api/v1/auth/login', route => route.fulfill({ status: 200, json: { access_token: 'fixture-token' } }));
    await page.goto(`${base}/auth.html`);
    await page.locator('[name=email]').fill('rimi@diu.edu.bd');
    await page.locator('[name=password]').fill('campus-demo-password');
    await page.locator('button[type=submit]').click();
    await page.waitForURL('**/dashboard.html');
    let semanticEnabled = false, submitted = '';
    await page.route('**/api/v1/metadata', route => route.fulfill({ json: {
      categories: [{ value: 'bag', en: 'Bag', bn: 'Bag' }],
      colors: [{ value: 'blue', en: 'Blue', bn: 'Blue' }],
      locations: [{ value: 'library', en: 'Library', bn: 'Library' }],
      consent_version: 'test', matching_mode: semanticEnabled ? 'hybrid' : 'local', semantic_enabled: semanticEnabled
    } }));
    await page.route('**/api/v1/items?type=*', async route => {
      submitted = route.request().postData();
      await route.fulfill({ status: 201, json: { id: 'intercepted-consent-fixture' } });
    });
    for (const enabled of [false, true]) {
      try {
        semanticEnabled = enabled;
        await page.goto(`${base}/report.html`);
        await page.getByText(enabled
          ? 'I agree to local matching and optional Gemini processing of my public description and photo.'
          : 'I agree to local processing of my public description and photo for matching.', { exact: true }).waitFor({ timeout: 4000 });
        await page.locator('[name=category]').selectOption('bag');
        await page.locator('[name=color]').selectOption('blue');
        await page.locator('[name=location]').selectOption('library');
        await page.locator('[name=title]').fill('Synthetic blue bag');
        await page.locator('[name=description]').fill('Blue bag with a white circle sticker.');
        await page.locator('[name=event_date]').fill('2026-11-15');
        await page.locator('[name=private_detail]').fill('Synthetic hidden verification mark');
        await page.locator('[name=consent]').check();
        await page.locator('button[type=submit]').click();
        await page.waitForURL('**/dashboard.html?created=1');
        assert.match(submitted, new RegExp(`name="semantic_consent"\\r?\\n\\r?\\n${String(enabled)}`));
        console.log(`PASS ${enabled ? 'hybrid' : 'local'} explicit consent form`);
      } catch (error) {
        failures.push(`consent ${enabled}: ${error.message}`);
      }
    }
    assert.deepEqual(failures, []);
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
