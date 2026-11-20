document.addEventListener('DOMContentLoaded', () => {
  if (!FinDIUSession.require()) return;
  const {el,text,link,shortDate,media,skeleton,errorState,confirm,toast} = FinDIUSession;
  const list=document.querySelector('[data-my-list]'), tabs=document.querySelector('[data-tabs]'), counters=document.querySelector('[data-counters]');
  const more=document.querySelector('[data-load-more]'), claimsNode=document.querySelector('[data-claims]'), claimsMore=document.querySelector('[data-more-claims]');
  const search=document.querySelector('[data-search]');
  let items=[],counts={},status='',next=null,total=0,query='',generation=0,busy=false,debounce,timer,claims=[],claimsOffset=null,claimsBusy=false;
  const statuses=['active','reserved','returned','archived'];
  function card(item) {
    const node=el('article','report-card'),body=el('div','card-body'),top=el('div','card-top');
    top.append(text('span',`badge badge--${item.type}`,`${item.type}_label`),text('span',`badge badge--${item.status}`,item.status));
    body.append(top,el('h3',null,item.title),el('p','card-meta',[item.category,item.color,item.brand,item.location].filter(Boolean).map(FinDIUI18n.label).join(' · ')+' · '+shortDate(item.event_date)));
    const foot=el('div','card-foot');
    foot.append(text('span','analysis',`analysis_${item.analysis || item.embed_status || 'pending'}`));
    if (item.matches_count || item.analysis==='ready') {
      const anchor=link('match_page',`match.html?id=${encodeURIComponent(item.id)}`);
      if (item.matches_count) anchor.textContent=FinDIUI18n.t('matches_count',{count:item.matches_count});
      foot.append(anchor);
    }
    body.append(foot);
    if(item.semantic_consent&&['pending','processing','failed'].includes(item.embed_status))body.append(text('p','hint',item.embed_status==='failed'?'semantic_failed':'semantic_pending'));
    if (item.status==='active') {
      const actions=el('div','row-actions'),archive=text('button','text-button','archive');archive.type='button';
      archive.addEventListener('click',async()=>{
        if (!await confirm('archive_confirm'))return;
        archive.disabled=true;
        try {await FinDIU.request(`/api/v1/items/${encodeURIComponent(item.id)}/archive`,{method:'POST'});await load();}
        catch(error){toast(FinDIUI18n.errorMessage(error));archive.disabled=false;}
      });
      actions.append(link('edit',`report.html?edit=${encodeURIComponent(item.id)}`),archive);body.append(actions);
    }
    node.append(media(item),body);return node;
  }
  function render() {
    counters.replaceChildren(...statuses.map(key=>{const node=el('div','counter');node.append(el('strong',null,counts[key] ?? '—'),text('span',null,key));return node;}));
    tabs.replaceChildren(...['',...statuses].map(key=>{
      const button=text('button','tab',key || 'all');button.type='button';button.setAttribute('aria-pressed',String(status===key));
      button.addEventListener('click',()=>{if(status===key)return;status=key;load();});return button;
    }));
    document.querySelector('[data-result-count]').textContent=FinDIUI18n.t('page_count',{start:total?1:0,end:items.length,count:total});
    if (items.length) list.replaceChildren(...items.map(card));
    else {const empty=el('div','empty');empty.append(text('h2',null,'no_reports'),text('p',null,'no_reports_copy'),link('new_report','report.html','button'));list.replaceChildren(empty);}
    list.removeAttribute('aria-busy');more.hidden=next===null;more.disabled=false;
  }
  function schedule() {
    clearTimeout(timer);
    if (document.hidden)return;
    if(items.some(item=>item.status==='active'&&(item.match_pending||['pending','processing'].includes(item.analysis)||item.semantic_consent&&['pending','processing'].includes(item.embed_status)))) timer=setTimeout(()=>load(false,true),15000);
  }
  async function load(append=false,quiet=false) {
    const run=++generation;busy=true;clearTimeout(timer);more.disabled=true;
    if(!append&&!quiet)skeleton(list,3);
    const offset=append?next:0;
    const qs=new URLSearchParams({mine:'true',limit:quiet?String(Math.max(items.length,12)):'12',offset:String(offset || 0)});
    if(status)qs.set('status',status);if(query)qs.set('q',query);
    try {
      const data=await FinDIU.request(`/api/v1/items?${qs}`);
      if(run!==generation)return;
      items=append?[...items,...data.items]:data.items;counts=data.counts || {};total=data.total;next=data.next_offset ?? null;render();
    } catch(error) {
      if(run!==generation)return;
      if(append||quiet){toast(FinDIUI18n.errorMessage(error));more.disabled=false;}
      else errorState(list,error,()=>load());
    } finally {if(run===generation){busy=false;list.removeAttribute('aria-busy');schedule();}}
  }
  function renderClaims() {
    claimsNode.replaceChildren(...(claims.length?claims.map(claim=>{
      const node=el('article','claim-lifecycle'),key=claim.returned_at?'returned':claim.status;
      const heading=el('div');heading.append(el('h3',null,FinDIUI18n.t('claim_ref',{id:claim.id.slice(0,8)})),el('p',null,shortDate(claim.created_at)));
      node.append(heading,text('span',`badge badge--${key}`,key));
      if(claim.review_note || claim.note)node.append(el('p','note',claim.review_note || claim.note));
      return node;
    }):[text('p','status-line','no_claims')]));
    claimsNode.removeAttribute('aria-busy');claimsMore.hidden=claimsOffset===null;claimsMore.disabled=false;
  }
  async function loadClaims(append=false) {
    if(claimsBusy)return;claimsBusy=true;claimsMore.disabled=true;
    if(!append)skeleton(claimsNode);
    try {
      const data=await FinDIU.request(`/api/v1/claims/mine?limit=20&offset=${append?claimsOffset:0}`),rows=data.claims;
      claims=append?[...claims,...rows]:rows;
      claimsOffset=claims.length<data.total?claims.length:null;renderClaims();
    } catch(error){if(append){toast(FinDIUI18n.errorMessage(error));claimsMore.disabled=false;}else errorState(claimsNode,error,()=>loadClaims());}
    finally{claimsBusy=false;}
  }
  search.addEventListener('input',()=>{clearTimeout(debounce);debounce=setTimeout(()=>{query=search.value.trim();load();},300);});
  more.addEventListener('click',()=>{if(!busy&&next!==null)load(true);});
  claimsMore.addEventListener('click',()=>loadClaims(true));
  document.addEventListener('visibilitychange',()=>{if(document.hidden)clearTimeout(timer);else if(!busy){load(false,true);loadClaims();}});
  window.addEventListener('pagehide',()=>{clearTimeout(timer);clearTimeout(debounce);});
  document.addEventListener('languagechange',()=>{if(!busy)render();if(!claimsBusy)renderClaims();});
  if(new URLSearchParams(location.search).has('created'))toast(FinDIUI18n.t('saved'));
  render();load();loadClaims();
});
