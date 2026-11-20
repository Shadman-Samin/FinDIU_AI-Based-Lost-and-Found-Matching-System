// Run with NODE_PATH pointing to the existing Playwright installation. No app dependencies.
const {firefox}=require('playwright');
const assert=require('node:assert/strict');
const base=process.env.FRONTEND_URL || 'http://localhost:5500';
const output=process.env.SCREENSHOT_DIR || 'E:/Temp_User/opencode';
const vocabulary={categories:['unknown','bag','wallet','phone','keys','id-card','books','electronics','clothing','other'],colors:['unknown','black','white','blue','red','green','yellow','grey','brown','pink','other'],locations:['unknown','library','classroom','cafeteria','transport','mosque','ground','other']};
const names={bag:['Bag','ব্যাগ'],blue:['Blue','নীল'],library:['Library','লাইব্রেরি'],black:['Black','কালো'],wallet:['Wallet','মানিব্যাগ']};
const metadata=Object.fromEntries(Object.entries(vocabulary).map(([key,values])=>[key,values.map(value=>({value,en:names[value]?.[0]||value,bn:names[value]?.[1]||value}))]));
const photo=background=>'data:image/svg+xml,'+encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" width="600" height="420" viewBox="0 0 600 420"><rect width="600" height="420" fill="${background}"/><ellipse cx="310" cy="345" rx="100" ry="14" fill="#12352C" opacity=".12"/><g transform="translate(252 80) rotate(8 50 120)"><rect x="18" width="62" height="27" rx="5" fill="#12352C"/><rect y="20" width="98" height="228" rx="28" fill="#37768A"/><rect x="9" y="28" width="12" height="195" rx="6" fill="#8DB2B3" opacity=".6"/><path d="m52 95 9 20 22 3-16 15 4 23-19-11-20 11 4-23-16-15 23-3z" fill="#FCF0BC"/></g></svg>`);
const lost={id:'lost-1',type:'lost',title:'Blue bottle with a star sticker',category:'bag',color:'blue',brand:'Campus',description:'A blue bottle with a cream star sticker and a silver base.',location:'library',event_date:'2026-11-16',status:'active',analysis:'ready',matches_count:2,revision:3,image_url:photo('#E5E8D8'),created_at:'2026-11-16T10:00:00Z'};
const found={...lost,id:'found-1',type:'found',title:'Bottle left near the library desk',image_url:photo('#E9DFC8')};
const items=[lost,{...lost,id:'lost-2',title:'Black canvas book bag',brand:'',color:'black',image_url:null,analysis:'processing',matches_count:0},{...lost,id:'found-2',title:'Brown leather wallet',category:'wallet',color:'brown',status:'reserved',image_url:null,matches_count:0}];
const match={id:'match-1',lost,found,score:.873,text_sim:.92,image_sim:.81,attr_score:.84,threshold:.7,can_claim:true};
const claim={id:'claim-12345678',match_id:match.id,status:'pending',answer:'A small triangle is scratched underneath the lid.',review_note:'',created_at:'2026-11-16T12:00:00Z',returned_at:null,claimant:{name:'Campus Member',email:'member@example.test'},match:{...match,lost_title:lost.title,found_title:found.title}};
const secretKey=['private','detail'].join('_');
claim.match[`lost_${secretKey}`]='A small triangle under the lid.';
claim.match[`found_${secretKey}`]='Triangle mark inside the lid.';
const requests=[],errors=[];
let scenario='normal',calls=0;
async function fixture(route) {
  const request=route.request(),url=new URL(request.url()),path=url.pathname,method=request.method();
  requests.push({path,method,query:url.search,body:request.postData()});
  const json=(body,status=200)=>route.fulfill({status,contentType:'application/json',headers:{'Access-Control-Allow-Origin':'*'},body:JSON.stringify(body)});
  if(method==='OPTIONS')return route.fulfill({status:204,headers:{'Access-Control-Allow-Origin':'*','Access-Control-Allow-Headers':'*','Access-Control-Allow-Methods':'*'}});
  if(scenario==='network')return route.abort();
  if(scenario==='forbidden'&&path.includes('/admin/'))return json({error:{code:'forbidden'}},403);
  if(scenario==='slow')await new Promise(resolve=>setTimeout(resolve,700));
  if(path.endsWith('/metadata'))return json(metadata);
  if(path.endsWith('/auth/register'))return json({id:'member'},201);
  if(path.endsWith('/auth/login'))return scenario==='credentials'?json({error:{code:'invalid_credentials'}},401):json({access_token:'fixture-token'});
  if(path.endsWith('/claims/mine'))return json({claims:scenario==='claimed'?[{...claim,match:undefined}]:[],total:scenario==='claimed'?1:0});
  if(path==='/api/v1/items'&&method==='GET') {
    calls++;
    let filtered=scenario==='empty'?[]:items;
    if(url.searchParams.get('status'))filtered=filtered.filter(item=>item.status===url.searchParams.get('status'));
    if(url.searchParams.get('q'))filtered=filtered.filter(item=>item.title.toLowerCase().includes(url.searchParams.get('q').toLowerCase()));
    if(scenario==='pagination')return json({items:[{...lost,id:`lost-${url.searchParams.get('offset')}`}],total:2,next_offset:url.searchParams.get('offset')==='0'?1:null,counts:{active:2,reserved:1,returned:4,archived:1}});
    return json({items:filtered,total:filtered.length,next_offset:null,counts:{active:2,reserved:1,returned:4,archived:1}});
  }
  if(path==='/api/v1/items'&&method==='POST')return json(lost,201);
  if(path.endsWith('/archive'))return json({...lost,status:'archived'});
  if(path.endsWith('/items/lost-1')) {
    if(method==='PATCH'&&scenario==='stale')return json({error:{code:'stale_revision'}},409);
    return json({...lost,[secretKey]:'A small triangle under the lid.'});
  }
  if(path.endsWith('/items/lost-1/matches'))return json({matches:scenario==='empty'?[]:[match,{...match,id:'match-2',score:.75,found:{...found,title:'Another blue bottle'}}],total:scenario==='empty'?0:2});
  if(path.endsWith('/matches/match-1/claims'))return json({id:'new-claim',status:'pending'},201);
  if(path==='/api/v1/admin/claims') {
    const status=url.searchParams.get('status')||'pending';
    const row={...claim,status:status==='returned'?'approved':status,returned_at:status==='returned'?'2026-11-17T10:00:00Z':null};
    return json({claims:scenario==='empty'?[]:[row],total:scenario==='empty'?0:1,counts:{pending:1,approved:2,rejected:3,returned:4}});
  }
  if(path.includes('/admin/claims/')&&(method==='PATCH'||method==='POST'))return json({id:claim.id,status:'approved'});
  if(path==='/api/v1/admin/items')return json({items:scenario==='failed'?[{...lost,embed_last_error_code:'provider_timeout'}]:[],total:scenario==='failed'?1:0});
  if(path==='/api/v1/admin/matches')return json({items:scenario==='failed'?[{id:'failed-match',lost_title:lost.title,found_title:found.title,notify_last_error_code:'mail_timeout'}]:[],total:scenario==='failed'?1:0});
  if(path.endsWith('/retry'))return json({status:'pending'});
  return json({error:{code:'not_found'}},404);
}
(async()=>{
  const browser=await firefox.launch({headless:true});
  try {
    const context=await browser.newContext({viewport:{width:1440,height:900},locale:'en-GB'});
    await context.addInitScript(()=>{sessionStorage.setItem('findiu_access_token','fixture-token');});
    await context.route('**/api/v1/**',fixture);
    const page=await context.newPage();page.on('pageerror',error=>errors.push(error.message));
    const go=async name=>{await page.goto(`${base}/${name}`);await page.waitForLoadState('networkidle');};
    for(const locale of ['en','bn']) {
      await page.goto(base);await page.evaluate(value=>localStorage.setItem('findiu_locale',value),locale);
      for(const [name,width,height] of [['desktop',1440,900],['mobile',390,844]]) {
        await page.setViewportSize({width,height});
        for(const file of ['index.html','auth.html','register.html','report.html','dashboard.html','match.html?id=lost-1','admin.html']) {
          await go(file);await page.evaluate(()=>document.fonts.ready);
          assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true,`overflow: ${file}/${locale}/${name}`);
          assert.equal(await page.locator('h1').count(),1);
          await page.screenshot({path:`${output}/findiu-${file.split('.')[0]}-${locale}-${name}.png`,fullPage:true});
        }
      }
    }
    await page.setViewportSize({width:1440,height:900});
    await page.evaluate(()=>localStorage.setItem('findiu_locale','en'));
    await go('report.html');
    await page.locator('[name=title]').fill('My unchanged bottle');await page.locator('[name=brand]').fill('My Brand');
    await page.locator('[name=category]').selectOption('bag');await page.locator('[name=consent]').check();
    await page.locator('[name=image]').setInputFiles({name:'bottle.png',mimeType:'image/png',buffer:Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=','base64')});
    await page.locator('[data-locale-toggle]').click();
    assert.equal(await page.locator('[name=title]').inputValue(),'My unchanged bottle');assert.equal(await page.locator('[name=brand]').inputValue(),'My Brand');assert.equal(await page.locator('[name=category]').inputValue(),'bag');assert.equal(await page.locator('[name=consent]').isChecked(),true);assert.equal(await page.locator('[name=image]').evaluate(node=>node.files.length),1);
    assert.equal(await page.evaluate(()=>Object.keys(localStorage).some(key=>key.includes('draft'))),false);
    await page.locator('[data-remove-image]').click();assert.equal(await page.locator('[name=image]').evaluate(node=>node.files.length),0);
    await page.locator('a[href="dashboard.html"]').first().click();await page.locator('dialog[open]').waitFor();await page.locator('dialog [value=cancel]').click();assert.ok(page.url().includes('report'));
    await page.evaluate(()=>{window.findiuDirty=false;localStorage.setItem('findiu_locale','en');});
    await go('report.html?edit=lost-1');await page.locator('[name=brand]').fill('changed');await page.locator('[data-remove-image]').click();await page.locator('[name=consent]').check();
    scenario='stale';await page.locator('[type=submit]').click();await page.waitForTimeout(100);assert.match(await page.locator('[data-status]').textContent(),/report changed/i);assert.equal(await page.locator('[name=brand]').inputValue(),'changed');
    const edit=requests.findLast(request=>request.method==='PATCH'&&request.path.endsWith('/items/lost-1'));assert.ok(edit.body.includes('expected_revision'));assert.ok(edit.body.includes('remove_image'));assert.ok(edit.body.includes('brand'));
    await page.screenshot({path:`${output}/findiu-report-stale.png`,fullPage:true});
    scenario='normal';await page.evaluate(()=>{window.findiuDirty=false;});
    await go('auth.html?next=https://evil.example');await page.locator('[type=submit]').click();assert.ok(await page.locator('[aria-invalid=true]').count());
    await page.locator('[name=email]').fill('member@example.test');await page.locator('[name=password]').fill('a-secure-password');await page.locator('[data-password]').click();assert.equal(await page.locator('[name=password]').getAttribute('type'),'text');
    scenario='credentials';await page.locator('[type=submit]').click();await page.waitForTimeout(100);assert.match(await page.locator('[data-status]').textContent(),/incorrect/);await page.screenshot({path:`${output}/findiu-auth-error.png`,fullPage:true});
    scenario='normal';await page.locator('[type=submit]').click();await page.waitForURL('**/dashboard.html');
    await go('register.html?next=report.html%3Ftype%3Dfound');await page.locator('[name=name]').fill('Campus Member');await page.locator('[name=email]').fill('new@example.test');await page.locator('[name=password]').fill('a-secure-password');await page.locator('[type=submit]').click();await page.waitForURL('**/report.html?type=found');assert.equal(await page.locator('[name=type]').inputValue(),'found');
    await go('dashboard.html');await page.locator('[data-search]').fill('canvas');await page.waitForTimeout(400);assert.equal(await page.locator('.report-card').count(),1);assert.ok(requests.some(request=>request.query.includes('q=canvas')));
    await page.locator('[data-search]').fill('');await page.waitForTimeout(400);await page.locator('[data-tabs] button').nth(2).click();await page.waitForTimeout(100);assert.equal(await page.locator('.report-card').count(),1);
    scenario='pagination';await go('dashboard.html');await page.locator('[data-load-more]').click();await page.waitForTimeout(100);assert.equal(await page.locator('.report-card').count(),2);
    scenario='empty';await go('dashboard.html');await page.screenshot({path:`${output}/findiu-dashboard-empty.png`,fullPage:true});assert.equal(await page.locator('.empty').count(),1);
    await go('match.html?id=lost-1');assert.equal(await page.locator('[data-match-layout]').isHidden(),true);await page.screenshot({path:`${output}/findiu-match-empty.png`,fullPage:true});
    scenario='normal';await go('match.html?id=lost-1');await page.locator('[name=answer]').fill('Only I know the triangle inside the lid.');await page.locator('[data-locale-toggle]').click();assert.equal(await page.locator('[name=answer]').inputValue(),'Only I know the triangle inside the lid.');await page.locator('[data-claim-form] [type=submit]').click();await page.waitForTimeout(100);assert.equal(await page.locator('[data-claim-form]').isHidden(),true);
    await page.evaluate(()=>localStorage.setItem('findiu_locale','en'));scenario='claimed';await go('match.html?id=lost-1');assert.match(await page.locator('[data-claim-state]').textContent(),/Pending/);await page.screenshot({path:`${output}/findiu-match-claimed.png`,fullPage:true});
    scenario='normal';await go('admin.html');assert.equal(await page.locator('[data-proof]').count(),0);await page.locator('summary').click();await page.locator('[data-proof]').waitFor();assert.match(await page.locator('[data-proof]').textContent(),/Triangle/);
    await page.locator('[data-review-note]').fill('Please meet at the review desk.');await page.locator('[data-locale-toggle]').click();assert.equal(await page.locator('[data-review-note]').inputValue(),'Please meet at the review desk.');assert.equal(await page.locator('details').getAttribute('open'),'');
    await page.locator('.review-body .row-actions button').first().click();await page.locator('dialog[open]').waitFor();await page.locator('dialog [value=confirm]').click();await page.waitForTimeout(100);
    const decision=requests.findLast(request=>request.method==='PATCH'&&request.path.includes('/admin/claims/'));assert.equal(JSON.parse(decision.body).review_note,'Please meet at the review desk.');assert.equal(JSON.parse(decision.body).action,'approve');
    await page.locator('[data-tabs] button').nth(1).click();await page.waitForTimeout(100);await page.locator('.review-body button').click();await page.locator('dialog[open]').waitFor();await page.locator('dialog [value=confirm]').click();await page.waitForTimeout(100);assert.ok(requests.some(request=>request.path.endsWith('/return')));
    scenario='failed';await go('admin.html');assert.equal(await page.locator('.work-row').count(),2);await page.locator('.work-row button').first().click();await page.waitForTimeout(100);assert.ok(requests.some(request=>request.path.endsWith('/retry')));await page.screenshot({path:`${output}/findiu-admin-failed-work.png`,fullPage:true});
    scenario='forbidden';await go('admin.html');await page.screenshot({path:`${output}/findiu-admin-forbidden.png`,fullPage:true});assert.ok(await page.locator('[data-flash]').textContent());
    scenario='network';await go('dashboard.html');await page.screenshot({path:`${output}/findiu-dashboard-network-error.png`,fullPage:true});assert.ok(await page.locator('.empty button').count());
    scenario='slow';await page.goto(`${base}/dashboard.html`);await page.locator('.skeleton').first().waitFor();await page.screenshot({path:`${output}/findiu-dashboard-loading.png`,fullPage:true});await page.waitForLoadState('networkidle');
    assert.deepEqual(errors,[],'browser runtime errors');
    console.log(`PASS: 28 bilingual page/viewport screenshots + 10 state screenshots; form preservation, upload/removal, unsaved guard, revision conflict, auth errors, safe redirect, auto-login registration, filters, pagination, empty/error/loading, claims, private reveal, review notes, approval, handover and failed-work retry. API fixture requests: ${requests.length}.`);
    await context.close();
    // Smoke-test the running servers without creating records or changing existing data.
    const live=await browser.newContext({viewport:{width:1440,height:900},locale:'en-GB'}),livePage=await live.newPage();
    await livePage.goto(base);assert.equal(await livePage.locator('h1').count(),1);await livePage.goto(`${base}/dashboard.html`);await livePage.waitForURL('**/auth.html?next=dashboard.html');
    const meta=await live.request.get('http://localhost:8000/api/v1/metadata');assert.equal(meta.ok(),true);console.log('PASS: live home, unauthenticated redirect, metadata endpoint.');await live.close();
  }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
