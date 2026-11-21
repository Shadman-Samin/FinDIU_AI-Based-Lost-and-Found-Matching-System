// Creates clearly labelled synthetic QA accounts/reports against an explicitly local QA API.
const assert = require('node:assert/strict');
const path = require('node:path');
const { firefox, request } = require('playwright');

const front = process.env.FINDIU_FRONTEND_URL || 'http://localhost:5500';
const api = process.env.FINDIU_QA_API_URL || 'http://localhost:8001';
const directory = process.env.FINDIU_QA_DIR || 'E:/Temp_User/opencode';
assert.ok(['localhost','127.0.0.1'].includes(new URL(api).hostname), 'QA API must be loopback');
const run = Date.now().toString(36), screenshots = [], errors = [];
const password = 'Synthetic-QA-password-123';
const proof = 'Synthetic label 77 beneath the lining';

(async () => {
  const browser = await firefox.launch({ headless: true });
  const http = await request.newContext({ baseURL: api });
  try {
    const metadata = await http.get('/api/v1/metadata');
    assert.equal((await metadata.json()).semantic_enabled, false, 'QA must not enable external AI');
    async function page() {
      const context = await browser.newContext({ locale: 'en-GB', viewport: { width: 1440, height: 900 } });
      const page = await context.newPage();
      page.on('pageerror', error => errors.push(error.message));
      await page.route('**/js/config.js', route => route.fulfill({ contentType: 'application/javascript', body: `window.FINDIU_CONFIG={apiBaseUrl:${JSON.stringify(api)}};` }));
      return page;
    }
    async function capture(page, name) {
      await page.evaluate(() => document.fonts.ready);
      for (const [size,width,height] of [['desktop',1440,900],['mobile',390,844]]) {
        await page.setViewportSize({ width, height });
        const filename = path.join(directory,`findiu-hybrid-qa-${run}-${name}-${size}.png`);
        await page.screenshot({ path: filename, fullPage: true });
        const overflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth);
        screenshots.push({ name, size, path: filename, overflow });
        assert.equal(overflow, false, `${name} ${size} must not overflow`);
      }
    }
    async function register(page, kind) {
      await page.goto(`${front}/register.html`);
      await page.locator('[name=name]').fill(`Synthetic QA ${kind}`);
      await page.locator('[name=email]').fill(`qa-${kind}-${run}@diu.edu.bd`);
      await page.locator('[name=password]').fill(password);
      await page.locator('button[type=submit]').click();
      await page.waitForURL('**/dashboard.html');
    }
    async function report(page, kind, options={}) {
      await page.goto(`${front}/report.html?type=${kind}`);
      await page.locator('[name=category] option[value=bag]').waitFor({ state: 'attached' });
      await page.locator('[name=category]').selectOption(options.category || 'bag');
      await page.locator('[name=color]').selectOption(options.color || 'blue');
      await page.locator('[name=brand]').fill(options.brand || 'Acme');
      await page.locator('[name=location]').selectOption(options.location || 'library');
      await page.locator('[name=title]').fill(options.title || (kind==='lost'?'Synthetic QA blue backpack':'Blue backpack white circle sticker'));
      await page.locator('[name=description]').fill(options.description || 'Blue backpack with a white circle sticker and broken left zipper.');
      await page.locator('[name=event_date]').fill('2026-11-15');
      await page.locator('[name=private_detail]').fill(kind==='lost'?proof:'Synthetic found mark 77 in the lining');
      if (options.photo !== false) {
        await page.locator('[name=image]').setInputFiles(path.resolve(`data/evaluation/synthetic-v1/images/tune-pair-00-${kind}.jpg`));
        await page.locator('[data-preview]').waitFor({ state: 'visible' });
        if (kind==='lost') {
          await page.locator('[data-remove-image]').click();
          assert.equal(await page.locator('[data-preview]').isVisible(), false);
          await page.locator('[name=image]').setInputFiles(path.resolve('data/evaluation/synthetic-v1/images/tune-pair-00-lost.jpg'));
        }
      }
      await page.locator('[name=consent]').check();
      if (options.capture) await capture(page,'report-local');
      const response = page.waitForResponse(response => response.url().includes(`/api/v1/items?type=${kind}`) && response.request().method()==='POST');
      await page.locator('button[type=submit]').click();
      const created = await response;
      assert.equal(created.status(),201,await created.text());
      const data = await created.json();
      assert.equal(data.semantic_consent,false);
      await page.waitForURL('**/dashboard.html?created=1');
      return data;
    }
    async function tick() {
      const response = await http.post('/internal/tick',{headers:{Authorization:'Bearer qa-local-tick'}});
      assert.equal(response.status(),200);
      assert.equal((await response.json()).embedded,0);
    }
    const owner = await page();
    await owner.goto(`${front}/index.html`); await capture(owner,'home');
    await owner.goto(`${front}/auth.html`); await capture(owner,'auth');
    await owner.goto(`${front}/register.html`); await capture(owner,'register');
    await register(owner,'owner');
    const lost = await report(owner,'lost',{capture:true});
    const finder = await page(); await register(finder,'finder');
    const found = await report(finder,'found');
    await tick();
    await owner.goto(`${front}/dashboard.html`);
    await owner.locator('.report-card').first().waitFor();
    await capture(owner,'dashboard');
    const ownerToken = await owner.evaluate(()=>FinDIU.token());
    const matches = await http.get(`/api/v1/items/${lost.id}/matches?limit=20`,{headers:{Authorization:`Bearer ${ownerToken}`}});
    const match = (await matches.json()).items.find(candidate=>(candidate.lost.id===lost.id&&candidate.found.id===found.id)||(candidate.lost.id===found.id&&candidate.found.id===lost.id));
    assert.ok(match,'QA reports must form a candidate pair');
    await owner.goto(`${front}/match.html?id=${lost.id}&match=${match.id}`);
    await owner.locator('[data-score]').waitFor({state:'visible'});
    await owner.locator('[data-comparison] details > summary').first().click();
    assert.equal(await owner.getByText('Local matching',{exact:true}).isVisible(),true);
    assert.ok(!await owner.locator('#main').innerText().then(text=>text.includes(proof)));
    await owner.getByText('Detailed signals',{exact:true}).click();
    await capture(owner,'match-en');
    await owner.locator('[data-locale-toggle]').click();
    await capture(owner,'match-bn');
    assert.ok((await owner.locator('.evidence').innerText()).includes('স্থানীয় ম্যাচিং'));
    await owner.locator('[data-locale-toggle]').click();
    assert.ok(match.score>=match.threshold);
    assert.equal(match.evidence.mode,'local');
    assert.ok(!JSON.stringify(match).includes(proof));
    const finderToken = await finder.evaluate(()=>FinDIU.token());
    assert.equal((await http.get(`/api/v1/items/${lost.id}`,{headers:{Authorization:`Bearer ${finderToken}`}})).status(),404);
    assert.equal((await http.post(`/api/v1/matches/${match.id}/claims`,{headers:{Authorization:`Bearer ${finderToken}`},data:{answer:'Synthetic unauthorized claim'}})).status(),404);
    await owner.locator('[data-open-verification]').click();
    await owner.locator('[data-verification-modal]').waitFor({state:'visible'});
    const claimResponse = owner.waitForResponse(response=>response.url().includes(`/matches/${match.id}/claims`) && response.request().method()==='POST');
    await owner.locator('[name=answer]').fill('The hidden label ends in 77 underneath the lining.');
    await owner.locator('[data-claim-form] button[type=submit]').click();
    const claimRequest = await claimResponse; assert.equal(claimRequest.status(),201);
    const claim = await claimRequest.json();
    await owner.locator('[data-claim-form]').waitFor({state:'hidden'});
    const admin = await page(); await admin.goto(`${front}/auth.html`);
    await admin.locator('[name=email]').fill('desk@diu.edu.bd');
    await admin.locator('[name=password]').fill('admin-password-123');
    await admin.locator('button[type=submit]').click(); await admin.waitForURL('**/dashboard.html');
    await admin.goto(`${front}/admin.html`);
    const card = admin.locator('.review-card').filter({hasText:claim.id.slice(0,8)});
    await card.waitFor();
    assert.ok(!(await card.innerText()).includes(proof));
    await card.locator('.private-details summary').click();
    await card.getByText(proof,{exact:true}).waitFor();
    await card.locator('.private-details summary').click();
    await card.locator('[name=review_note]').fill('Synthetic QA proof checked; await physical handover.');
    await capture(admin,'admin-en');
    await admin.locator('[data-locale-toggle]').click();
    await capture(admin,'admin-bn');
    assert.equal(await card.locator('[name=review_note]').inputValue(),'Synthetic QA proof checked; await physical handover.');
    await admin.locator('[data-locale-toggle]').click();
    await card.locator('button[data-i18n=approve]').click();
    await admin.locator('[data-dialog]').waitFor({state:'visible'});
    await admin.locator('[data-dialog] button[value=confirm]').click();
    await admin.locator('[data-tabs] button').filter({hasText:/Approved/}).click();
    await card.locator('button[data-i18n=handover]').waitFor();
    const returnResponse = admin.waitForResponse(response=>response.url().includes(`/claims/${claim.id}/return`));
    await card.locator('button[data-i18n=handover]').click();
    await admin.locator('[data-dialog] button[value=confirm]').click();
    const returned = await returnResponse; assert.equal(returned.status(),200);
    const returnData = await returned.json();
    const adminToken = await admin.evaluate(()=>FinDIU.token());
    const repeated = await http.post(`/api/v1/admin/claims/${claim.id}/return`,{headers:{Authorization:`Bearer ${adminToken}`}});
    assert.equal((await repeated.json()).returned_at,returnData.returned_at);
    for (const id of [lost.id,found.id]) {
      const response = await http.get(`/api/v1/admin/items?limit=100`,{headers:{Authorization:`Bearer ${adminToken}`}});
      assert.equal((await response.json()).items.find(item=>item.id===id).status,'returned');
    }
    const unmatched = await report(owner,'lost',{photo:false,category:'books',color:'yellow',brand:'QA RibbonMaker',location:'mosque',title:'Synthetic QA yellow folio',description:'Yellow folio with checker-pattern cover and a green ribbon bookmark.'});
    await tick();
    await owner.goto(`${front}/match.html?id=${unmatched.id}`);
    await owner.getByText('No candidates yet.',{exact:true}).waitFor();
    await capture(owner,'no-candidate');
    await owner.goto(`${front}/report.html?edit=${unmatched.id}`);
    await owner.waitForFunction(()=>!document.querySelector('[data-report-form]')?.hasAttribute('aria-busy')&&!document.querySelector('[data-report-form] button[type=submit]')?.disabled);
    await owner.locator('[name=title]').fill('Synthetic QA revised yellow folio');
    await owner.locator('[name=consent]').check();
    await owner.locator('button[type=submit]').click(); await owner.waitForURL('**/dashboard.html?created=1');
    const folio = owner.locator('.report-card').filter({has:owner.getByText('Synthetic QA revised yellow folio',{exact:true})});
    await folio.locator('button[data-i18n=archive]').click();
    await owner.locator('[data-dialog] button[value=confirm]').click();
    await owner.locator('[data-search]').fill('revised');
    await owner.waitForFunction(()=>document.querySelectorAll('.report-card').length===1 && document.querySelector('.report-card')?.textContent.includes('Archived'));
    await owner.locator('[data-search]').fill('');
    await owner.route('**/api/v1/items?mine=*',route=>route.fulfill({status:503,json:{error:{code:'database_unavailable',message:'Synthetic QA temporary outage'}}}));
    await owner.reload();
    await owner.locator('[data-my-list] button[data-i18n=retry]').waitFor();
    await capture(owner,'dashboard-error');
    await owner.unroute('**/api/v1/items?mine=*');
    await owner.locator('[data-my-list] button[data-i18n=retry]').click();
    await owner.locator('.report-card').first().waitFor();
    assert.deepEqual(errors,[]);
    console.log(JSON.stringify({run,verified:['registration','photo-preview/removal','local-consent','local-match-evidence','bilingual-ledger','privacy/owner-denial','claim','admin-note-preservation','approval','handover/idempotency','no-candidate','edit/archive','search','error/retry'],screenshots},null,2));
  } finally {
    await http.dispose(); await browser.close();
  }
})().catch(error=>{console.error(error);process.exitCode=1;});
