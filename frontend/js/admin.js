document.addEventListener('DOMContentLoaded', () => {
  if(!FinDIUSession.require())return;
  const {el,text,score,skeleton,errorState,confirm,toast}=FinDIUSession;
  const list=document.querySelector('[data-claims]'),failed=document.querySelector('[data-failed-work]');
  const prev=document.querySelector('[data-prev]'),next=document.querySelector('[data-next]'),moreWork=document.querySelector('[data-more-work]');
  const flash=document.querySelector('[data-flash]');
  let rows=[],counts={},status='pending',offset=0,total=0,generation=0,busy=false;
  let failedItems=[],failedMatches=[],itemOffset=0,matchOffset=0,itemTotal=0,matchTotal=0,workBusy=false;
  const notes=new Map(),revealed=new Set(),expanded=new Map(),statuses=['pending','approved','rejected','returned'];
  function saveInputs() {
    list.querySelectorAll('[data-review-note]').forEach(input=>notes.set(input.dataset.reviewNote,input.value));
    list.querySelectorAll('[data-private-id]').forEach(details=>{if(details.open)revealed.add(details.dataset.privateId);else revealed.delete(details.dataset.privateId);});
    list.querySelectorAll('.match-comparison[data-claim-id]').forEach(card=>expanded.set(card.dataset.claimId,Array.from(card.querySelectorAll('details')).map(node=>node.open)));
  }
  async function decide(claim,action,button,note) {
    if(!await confirm(action==='return'?'handover_confirm':`${action}_confirm`))return;
    button.disabled=true;
    try {
      await FinDIU.request(`/api/v1/admin/claims/${encodeURIComponent(claim.id)}${action==='return'?'/return':''}`,action==='return'?{method:'POST'}:{method:'PATCH',body:{action,review_note:note.value.trim()}});
      notes.delete(claim.id);revealed.delete(claim.id);expanded.delete(claim.id);await load();toast(FinDIUI18n.t('decision_saved'));
    }catch(error){if(error.status===409)await load();toast(FinDIUI18n.errorMessage(error));button.disabled=false;}
  }
  function claimRow(claim) {
    const node=el('article','review-card'),head=el('div','review-head'),heading=el('div');
    const state=claim.returned_at?'returned':claim.status;
    heading.append(text('span',`badge badge--${state}`,state),text('h2',null,'claim_ref',{id:claim.id.slice(0,8)}),el('p','muted',`${claim.claimant.name} · ${claim.claimant.email}`));
    const stamp=el('div','score-chip');stamp.append(el('strong',null,score(claim.match.score)),text('span',null,'similarity'));head.append(heading,stamp);
    const body=el('div','review-body'),pair=el('div','comparison-pair');
    const comparison=FinDIUComponents.MatchComparisonCard(claim.match,claim.match.lost.id);comparison.dataset.claimId=claim.id;
    comparison.querySelectorAll('details').forEach((node,index)=>{node.open=expanded.get(claim.id)?.[index] ?? false;});
    body.append(FinDIUComponents.StatusStepper(claim),comparison);
    const answer=el('div','answer-block');answer.append(text('p','eyebrow','claimant_says'),el('p',null,claim.answer));body.append(answer);
    const privateBox=el('details','private-details');privateBox.dataset.privateId=claim.id;privateBox.open=revealed.has(claim.id);
    const summary=text('summary',null,'reveal');privateBox.append(summary);
    // Private proof is inserted only while an authorised reviewer reveals it.
    function reveal() {
      privateBox.querySelector('[data-proof]')?.remove();
      if(!privateBox.open){revealed.delete(claim.id);return;}
      revealed.add(claim.id);const proof=el('div');proof.dataset.proof='';
      proof.append(text('span','eyebrow','hidden_detail'),el('p',null,claim.match.lost_private_detail),text('span','eyebrow','finder_detail'),el('p',null,claim.match.found_private_detail));privateBox.append(proof);
    }
    privateBox.addEventListener('toggle',reveal);if(privateBox.open)reveal();body.append(privateBox);
    if(claim.status==='pending') {
      const label=el('label','field'),note=el('textarea');note.name='review_note';note.maxLength=1000;note.rows=2;note.dataset.reviewNote=claim.id;note.value=notes.get(claim.id) ?? claim.review_note ?? '';
      note.addEventListener('input',()=>notes.set(claim.id,note.value));
      const help=text('span','hint','review_help');help.id=`review-help-${claim.id}`;note.setAttribute('aria-describedby',help.id);
      label.append(text('span',null,'review_note'),note,help);body.append(label);
      const actions=el('div','row-actions');actions.style.marginTop='18px';
      ['approve','reject'].forEach(action=>{const button=text('button',`button small ${action==='reject'?'button-light':''}`,action);button.type='button';button.addEventListener('click',()=>decide(claim,action,button,note));actions.append(button);});body.append(actions);
    } else {
      if(claim.review_note) {const note=el('div','answer-block');note.append(text('p','eyebrow','review_note'),el('p',null,claim.review_note));body.append(note);}
      if(claim.status==='approved'&&!claim.returned_at) {const button=text('button','button small','handover');button.type='button';button.addEventListener('click',()=>decide(claim,'return',button));body.append(button);}
    }
    node.append(head,body);return node;
  }
  function renderNavigation() {
    document.querySelector('[data-counters]').replaceChildren(...statuses.map(key=>{const node=el('div','counter');node.append(el('strong',null,counts[key] ?? '—'),text('span',null,key));return node;}));
    document.querySelector('[data-tabs]').replaceChildren(...statuses.map(key=>{
      const button=el('button','tab',`${FinDIUI18n.t(key)} (${counts[key] ?? '—'})`);button.type='button';button.setAttribute('aria-pressed',String(key===status));
      button.addEventListener('click',()=>{if(key===status)return;saveInputs();status=key;offset=0;load();});return button;
    }));
  }
  function render() {
    renderNavigation();
    list.replaceChildren(...(rows.length?rows.map(claimRow):[text('div','empty','queue_clear')]));list.removeAttribute('aria-busy');
    prev.disabled=offset===0;next.disabled=offset+rows.length>=total;
    document.querySelector('[data-page-info]').textContent=FinDIUI18n.t('page_count',{start:total?offset+1:0,end:offset+rows.length,count:total});
  }
  async function load() {
    saveInputs();const run=++generation;busy=true;prev.disabled=true;next.disabled=true;skeleton(list);
    try {
      const data=await FinDIU.request(`/api/v1/admin/claims?status=${status}&limit=10&offset=${offset}`);
      if(run!==generation)return;
      rows=data.claims;counts=data.counts || {};total=data.total;
      if(offset&&offset>=total){offset=Math.max(0,Math.ceil(total/10)*10-10);return load();}
      flash.textContent='';render();
    }catch(error){if(run!==generation)return;errorState(list,error,load);if(error.status===403){flash.dataset.i18n='no_admin';FinDIUI18n.render();}}
    finally{if(run===generation)busy=false;}
  }
  function renderWork() {
    const work=[];
    for(const [items,type] of [[failedItems,'items'],[failedMatches,'matches']])items.forEach(item=>{
      const row=el('article','work-row'),detail=el('div');
       detail.append(text('p','eyebrow',type==='items'?'semantic_failed':'failed_notification'),el('h3',null,type==='items'?item.title:`${item.lost_title} / ${item.found_title}`),el('p',null,item.embed_last_error_code || item.notify_last_error_code || FinDIUI18n.t('unknown_failure')));
       if(type==='items'&&!item.semantic_consent){row.append(detail,text('p','hint','semantic_not_consented'));work.push(row);return;}
      const retry=text('button','button button-light small','retry');retry.type='button';
      retry.addEventListener('click',async()=>{
        retry.disabled=true;
        try{await FinDIU.request(`/api/v1/admin/${type}/${encodeURIComponent(item.id)}/retry`,{method:'POST'});await loadWork();toast(FinDIUI18n.t('retry_queued'));}
        catch(error){if(error.status===409)await loadWork();toast(FinDIUI18n.errorMessage(error));retry.disabled=false;}
      });row.append(detail,retry);work.push(row);
    });
    failed.replaceChildren(...(work.length?work:[text('p','status-line','no_failed_work')]));failed.removeAttribute('aria-busy');
    moreWork.hidden=itemOffset>=itemTotal&&matchOffset>=matchTotal;moreWork.disabled=false;
  }
  async function loadWork(append=false) {
    if(workBusy)return;workBusy=true;moreWork.disabled=true;
    if(!append)skeleton(failed);
    try {
      const [items,matches]=await Promise.all([
        !append||itemOffset<itemTotal?FinDIU.request(`/api/v1/admin/items?embed_status=failed&limit=20&offset=${append?itemOffset:0}`):Promise.resolve(null),
        !append||matchOffset<matchTotal?FinDIU.request(`/api/v1/admin/matches?notify_status=failed&limit=20&offset=${append?matchOffset:0}`):Promise.resolve(null)
      ]);
      if(items){failedItems=append?[...failedItems,...items.items]:items.items;itemOffset=failedItems.length;itemTotal=items.total;}
      if(matches){failedMatches=append?[...failedMatches,...matches.items]:matches.items;matchOffset=failedMatches.length;matchTotal=matches.total;}
      renderWork();
    }catch(error){if(append){toast(FinDIUI18n.errorMessage(error));moreWork.disabled=false;}else errorState(failed,error,()=>loadWork());}
    finally{workBusy=false;}
  }
  prev.addEventListener('click',()=>{offset=Math.max(0,offset-10);load();});next.addEventListener('click',()=>{offset+=10;load();});
  document.querySelector('[data-refresh-work]').addEventListener('click',()=>loadWork());moreWork.addEventListener('click',()=>loadWork(true));
   document.addEventListener('languagechange',()=>{if(!busy){saveInputs();render();}if(!workBusy)renderWork();});
  load();loadWork();
});
