document.addEventListener('DOMContentLoaded', () => {
  if(!FinDIUSession.require())return;
  const {el,text,link,score,threshold:formatThreshold,evidence,itemComparison,skeleton,errorState,valid,formErrors,toast}=FinDIUSession;
  const params=new URLSearchParams(location.search),itemId=params.get('id'),wanted=params.get('match');
  if(!itemId){location.replace('dashboard.html');return;}
  const state=document.querySelector('[data-match-state]'),layout=document.querySelector('[data-match-layout]');
  const form=document.querySelector('[data-claim-form]'),claimState=document.querySelector('[data-claim-state]'),claimLink=document.querySelector('[data-claim-link]');
  const more=document.querySelector('[data-more-candidates]');
  const openVerification=document.querySelector('[data-open-verification]'),modal=FinDIUComponents.VerificationModal(form);
  openVerification.addEventListener('click',()=>{if(match?.can_claim&&!existing)modal.open();});
  let item,matches=[],match,existing,claims=[],offset=0,total=0;
  function render() {
    document.querySelector('[data-match-title]').textContent=item.title;
    state.replaceChildren();state.removeAttribute('aria-busy');
    if(!matches.length) {
      layout.hidden=true;const empty=el('div','empty');
      empty.append(text('h2',null,'no_candidate'),text('p',null,'no_candidate_copy'),link('back','dashboard.html','button button-light'));state.append(empty);return;
    }
    layout.hidden=false;
    const self=match.lost.id===item.id?match.lost:match.found,other=match.lost.id===item.id?match.found:match.lost;
    const comparison=document.querySelector('[data-comparison]');
    const expanded=Array.from(comparison.querySelectorAll('details')).map(node=>node.open);
    comparison.replaceChildren(FinDIUComponents.MatchComparisonCard(match,item.id));
    comparison.querySelectorAll('details').forEach((node,index)=>{node.open=expanded[index] || false;});
    existing=claims.find(claim=>claim.match_id===match.id);
    form.hidden=!match.can_claim||Boolean(existing);
    openVerification.hidden=form.hidden;
    claimLink.hidden=!existing;
    claimState.textContent=existing?FinDIUI18n.t(existing.returned_at?'returned':existing.status):match.can_claim?'':FinDIUI18n.t('cannot_claim');
    if(existing?.review_note)claimState.append(el('p',null,existing.review_note));
    if(existing)claimState.append(FinDIUComponents.StatusStepper(existing));
    const list=document.querySelector('[data-more]');
    list.replaceChildren(...matches.filter(candidate=>candidate.id!==match.id).map(candidate=>{
      const otherItem=candidate.lost.id===item.id?candidate.found:candidate.lost;
      const anchor=el('a','candidate-row');anchor.href=`match.html?id=${encodeURIComponent(itemId)}&match=${encodeURIComponent(candidate.id)}`;
      anchor.append(el('span',null,otherItem.title),el('strong',null,score(candidate.score)));return anchor;
    }));
    if(matches.length===1&&total===1)list.append(text('p','hint','no_candidate'));
    more.hidden=offset>=total;
  }
  async function load() {
    layout.hidden=true;skeleton(state);
    try {
      const [own,data,claimData]=await Promise.all([FinDIU.request(`/api/v1/items/${encodeURIComponent(itemId)}`),FinDIU.request(`/api/v1/items/${encodeURIComponent(itemId)}/matches?limit=20`),FinDIU.request('/api/v1/claims/mine?limit=100')]);
      item=own;matches=data.matches;offset=matches.length;total=data.total;claims=claimData.claims;
      // A selected candidate may be beyond the first page.
      if(wanted&&!matches.some(candidate=>candidate.id===wanted)) {
        const selected=await FinDIU.request(`/api/v1/matches/${encodeURIComponent(wanted)}`);
        if(selected.lost.id!==itemId&&selected.found.id!==itemId)throw {status:404,payload:{error:{code:'not_found'}}};
        matches.push(selected);
      }
      match=matches.find(candidate=>candidate.id===wanted)||matches[0];render();
    } catch(error){errorState(state,error,load);}
  }
  form.addEventListener('submit',async event=>{
    event.preventDefault();if(!valid(form))return;
    const button=form.querySelector('[type=submit]');button.disabled=true;
    try {
      const result=await FinDIU.request(`/api/v1/matches/${encodeURIComponent(match.id)}/claims`,{method:'POST',body:{answer:form.elements.answer.value.trim()}});
      claims.push({...result,match_id:match.id});match.can_claim=false;modal.close();render();toast(FinDIUI18n.t('claim_sent'));
    }catch(error){formErrors(form,error);}
    finally{button.disabled=false;}
  });
  more.addEventListener('click',async()=>{
    more.disabled=true;
    try {
      const data=await FinDIU.request(`/api/v1/items/${encodeURIComponent(itemId)}/matches?limit=20&offset=${offset}`);
      offset+=data.matches.length;total=data.total;const ids=new Set(matches.map(candidate=>candidate.id));matches.push(...data.matches.filter(candidate=>!ids.has(candidate.id)));render();
    }catch(error){toast(FinDIUI18n.errorMessage(error));}finally{more.disabled=false;}
  });
  document.addEventListener('languagechange',()=>{if(item)render();});
  load();
});
