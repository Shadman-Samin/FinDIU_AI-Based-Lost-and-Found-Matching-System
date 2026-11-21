(function () {
  const {el,text,link,media,shortDate,score,threshold,evidence,itemComparison}=FinDIUSession;
  // Copy only public fields before a reusable view can retain an item.
  function publicItem(item) {
    const result={};
    ['id','type','status','title','description','category','color','brand','location','event_date','image_url','is_sensitive','analysis','embed_status','matches_count','semantic_consent'].forEach(key=>{result[key]=item[key];});
    return result;
  }
  function ItemCard(input) {
    const item=publicItem(input),node=el('article','report-card'),body=el('div','card-body'),top=el('div','card-top');
    top.append(text('span',`badge badge--${item.type}`,`${item.type}_label`),text('span',`badge badge--${item.status}`,item.status));
    const meta=el('p','card-meta');
    meta.dataset.itemMeta=JSON.stringify([item.category,item.color,item.brand,item.location,item.event_date]);
    meta.textContent=[item.category,item.color,item.brand,item.location].filter(Boolean).map(FinDIUI18n.label).join(' · ')+' · '+shortDate(item.event_date);
    body.append(top,el('h3',null,item.title),meta);
    const foot=el('div','card-foot');foot.append(text('span','analysis',`analysis_${item.analysis || item.embed_status || 'pending'}`));
    if(item.matches_count || item.analysis==='ready')foot.append(link(item.matches_count?'matches_count':'match_page',`match.html?id=${encodeURIComponent(item.id)}`));
    if(item.matches_count){const anchor=foot.querySelector('a');anchor.dataset.i18nValues=JSON.stringify({count:item.matches_count});anchor.textContent=FinDIUI18n.t('matches_count',{count:item.matches_count});}
    body.append(foot);
    if(item.semantic_consent&&['pending','processing','failed'].includes(item.embed_status))body.append(text('p','hint',item.embed_status==='failed'?'semantic_failed':'semantic_pending'));
    node.append(media(item),body);return node;
  }
  function SearchFilterBar(root,onChange) {
    const searchLabel=text('label','search-field','search');
    const search=el('input');search.type='search';search.maxLength=80;search.dataset.search='';search.dataset.i18nPlaceholder='search_placeholder';searchLabel.append(search);
    const row=el('div','filter-row'),types=el('div','tabs'),selects=el('div','filter-selects');
    let type='',metadata;
    const controls={};
    function values(){return {q:search.value.trim(),type,...Object.fromEntries(Object.entries(controls).map(([key,node])=>[key,node.value]))};}
    ['', 'lost','found'].forEach(key=>{
      const button=text('button','tab',key?`${key}_label`:'all');button.type='button';button.dataset.filterType=key;button.setAttribute('aria-pressed',String(!key));
      button.addEventListener('click',()=>{type=key;types.querySelectorAll('button').forEach(node=>node.setAttribute('aria-pressed',String(node===button)));onChange(values());});types.append(button);
    });
    ['category','location','status'].forEach(key=>{
      const label=el('label','filter-field'),select=el('select');label.append(text('span','sr-only',key==='status'?'report_status':key),select);select.dataset.filter=key;controls[key]=select;
      select.addEventListener('change',()=>onChange(values()));selects.append(label);
    });
    function options(){
      for(const [key,node] of Object.entries(controls)){
        const current=node.value,entries=key==='status'?['active','reserved','returned','archived'].map(value=>({value,en:FinDIUI18n.t(value),bn:FinDIUI18n.t(value)})):metadata?.[key==='category'?'categories':'locations'] || [];
        node.replaceChildren(new Option(FinDIUI18n.t(`all_${key}`),''),...entries.map(entry=>new Option(entry[FinDIUI18n.locale],entry.value)));node.value=current;
      }
      search.placeholder=FinDIUI18n.t('search_placeholder');
    }
    const reset=text('button','button button-light','reset_filters');reset.type='button';reset.dataset.resetFilters='';
    reset.addEventListener('click',()=>{search.value='';type='';Object.values(controls).forEach(node=>node.value='');types.querySelectorAll('button').forEach(node=>node.setAttribute('aria-pressed',String(node.dataset.filterType==='')));onChange(values());search.focus();});
    // A separate text span avoids language rendering replacing the input.
    searchLabel.removeAttribute('data-i18n');searchLabel.firstChild.replaceWith(text('span','sr-only','search'));
    search.addEventListener('input',()=>onChange(values(),true));row.append(types,selects,reset);root.replaceChildren(searchLabel,row);options();
    document.addEventListener('languagechange',options);
    return {search,setMetadata(data){metadata=data;options();},reset(){reset.click();}};
  }
  function MatchComparisonCard(input,ownId) {
    const self=publicItem(input.lost.id===ownId?input.lost:input.found),other=publicItem(input.lost.id===ownId?input.found:input.lost);
    const card=el('article','match-comparison'),head=el('div','comparison-head'),value=el('strong','badge badge--match',input.score==null?FinDIUI18n.t('not_recorded'):score(input.score));value.dataset.score='';
    const ref=el('span','meta',input.id?.slice(0,8) || '');ref.dataset.matchRef='';head.append(value,text('span','hint','similarity'),ref);
    const pair=el('div','comparison-pair');pair.dataset.pair='';pair.append(itemComparison(self,'own_report'),itemComparison(other,'candidate'));
    const detail=el('details','comparison-details');detail.append(text('summary',null,'comparison_evidence'));
    const evidenceBox=el('div');evidenceBox.dataset.evidence='';evidenceBox.append(evidence(input));
    const limit=el('p','hint');limit.append(text('span',null,'threshold'),document.createTextNode(': '));const recorded=el('strong',null,threshold(input.threshold));recorded.dataset.threshold='';limit.append(recorded);
    const clues=el('div','clue-stamps');clues.dataset.clues='';clues.append(text('p','hint','inferred'));
    const same=['category','color','location','event_date','brand'].filter(key=>self[key]&&self[key]!=='unknown'&&self[key]===other[key]);
    if(same.length)same.forEach(key=>clues.append(text('span','clue',`same_${key==='event_date'?'date':key}`)));else clues.append(text('span','clue','no_clues'));
    detail.append(evidenceBox,limit,clues);card.append(head,pair,detail);return card;
  }
  function LiveMatchSidebar(input,matches=[]) {
    const box=el('details','live-match-sidebar');box.open=true;
    const summary=text('summary',null,'saved_candidates');box.append(summary,text('p','hint',input?'saved_candidates_note':'matching_after_publish'));
    if(input&&matches.length){
      box.classList.add('has-candidates');
      matches.forEach(match=>{
        const other=publicItem(match.lost.id===input.id?match.found:match.lost),anchor=el('a','candidate-row');anchor.href=`match.html?id=${encodeURIComponent(input.id)}&match=${encodeURIComponent(match.id)}`;
        anchor.append(el('span',null,other.title),el('strong',null,match.score==null?FinDIUI18n.t('not_recorded'):score(match.score)));box.append(anchor);
      });
    }else box.append(text('p','sidebar-note',input?'no_candidate':'publish_first'));
    return box;
  }
  function VerificationModal(form) {
    const dialog=el('dialog','verification-dialog');dialog.dataset.verificationModal='';dialog.setAttribute('aria-labelledby','verification-title');dialog.setAttribute('aria-describedby','verification-help');
    const heading=text('h2',null,'verification');heading.id='verification-title';const help=text('p','hint','answer_help');help.id='verification-help';
    const cancel=text('button','button button-light','cancel');cancel.type='button';cancel.addEventListener('click',()=>dialog.close());form.querySelector('.actions').prepend(cancel);
    dialog.append(heading,help,form);document.body.append(dialog);
    dialog.addEventListener('close',()=>{form.reset();FinDIUSession.formErrors(form);const status=form.querySelector('[data-status]');status.removeAttribute('data-i18n');status.textContent='';});
    return {open(){dialog.showModal();form.elements.answer.focus();},close(){dialog.close();}};
  }
  function StatusStepper(claim) {
    const returned=Boolean(claim.returned_at),rejected=claim.status==='rejected';
    const stage=returned?3:claim.status==='approved'?2:1;
    const box=el('div','lifecycle'),list=el('ol','status-stepper');list.setAttribute('aria-label',FinDIUI18n.t('claim_progress'));
    ['reported','claim_submitted','verified','returned'].forEach((key,index)=>{
      const node=el('li',index<stage?'complete':index===stage&&!rejected?'current':'');
      node.append(el('span','step-dot',String(index+1)),text('span',null,key));if(index===stage&&!rejected)node.setAttribute('aria-current','step');list.append(node);
    });
    box.append(list,text('p','hint',rejected?'rejected_note':returned?'handover_recorded':'handover_info'));return box;
  }
  window.FinDIUComponents={ItemCard,SearchFilterBar,MatchComparisonCard,LiveMatchSidebar,VerificationModal,StatusStepper};
})();
