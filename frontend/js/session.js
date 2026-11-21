(function () {
  function require() {
    if (FinDIU.token()) return true;
    location.replace(`auth.html?next=${encodeURIComponent(location.pathname.split('/').pop() + location.search)}`);
    return false;
  }
  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }
  function text(tag, className, key, values) {
    const node = el(tag, className, FinDIUI18n.t(key, values));
    node.dataset.i18n = key;
    if (values) node.dataset.i18nValues = JSON.stringify(values);
    return node;
  }
  function link(key, href, className) {
    const node = text('a', className, key);
    node.href = href;
    return node;
  }
  function shortDate(value) {
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? value || '' : date.toLocaleDateString(FinDIUI18n.locale === 'bn' ? 'bn-BD' : 'en-GB', {day:'numeric',month:'short',year:'numeric'});
  }
  function toast(message) {
    const node = document.querySelector('[data-toast]');
    node.textContent = message;
    clearTimeout(toast.timer);
    toast.timer = setTimeout(() => { node.textContent = ''; }, 7000);
  }
  function confirm(key) {
    return new Promise(resolve => {
      const dialog = document.querySelector('[data-dialog]');
      dialog.querySelector('[data-dialog-message]').dataset.i18n = key;
      FinDIUI18n.render(dialog);
      dialog.returnValue = '';
      dialog.addEventListener('close', () => resolve(dialog.returnValue === 'confirm'), {once:true});
      dialog.showModal();
      dialog.querySelector('[value=cancel]').focus();
    });
  }
  function formErrors(form, error) {
    form.querySelectorAll('[data-field-error]').forEach(node => node.remove());
    form.querySelectorAll('[aria-invalid]').forEach(node => { node.removeAttribute('aria-invalid'); node.removeAttribute('aria-errormessage'); });
    if (!error) return;
    let first;
    const fields = error.payload?.error?.fields || [];
    fields.forEach(entry => {
      const input = form.elements.namedItem(entry.field);
      if (!input?.tagName) return;
      const node = text('span', 'field-error', 'required');
      node.dataset.fieldError = '';
      node.id = `error-${entry.field}`;
      input.setAttribute('aria-invalid', 'true');
      input.setAttribute('aria-errormessage', node.id);
      input.closest('.field')?.append(node);
      first ||= input;
    });
    const status = form.querySelector('[data-status]');
    if (status) { status.dataset.i18n = FinDIUI18n.errorKey(error); status.textContent = FinDIUI18n.errorMessage(error); status.tabIndex = -1; }
    (first || status)?.focus();
  }
  function valid(form) {
    formErrors(form);
    const invalid = Array.from(form.elements).filter(input => {
      if (!input.willValidate) return false;
      if (input.tagName === 'TEXTAREA' || (input.tagName === 'INPUT' && ['text','email'].includes(input.type))) {
        const value = input.value.trim();
        input.setCustomValidity((input.required && !value) || (value && input.minLength > 0 && value.length < input.minLength) ? FinDIUI18n.t('required') : '');
      }
      return !input.checkValidity();
    });
    if (!invalid.length) return true;
    formErrors(form, {status:422,payload:{error:{code:'validation_error',fields:invalid.map(input => ({field:input.name}))}}});
    return false;
  }
  function skeleton(node, count = 1) {
    node.setAttribute('aria-busy', 'true');
    node.replaceChildren(...Array.from({length:count}, () => {
      const item = el('div', 'skeleton'); item.setAttribute('aria-hidden', 'true'); return item;
    }));
  }
  function errorState(node, error, retry) {
    node.removeAttribute('aria-busy');
    const box = el('div', 'empty');
    box.append(text('p', null, FinDIUI18n.errorKey(error)));
    const button = text('button', 'button button-light', 'retry');
    button.type = 'button'; button.addEventListener('click', retry);
    box.append(button); node.replaceChildren(box);
  }
  function media(item) {
    const sensitive=item.is_sensitive===true,imageURL=item.image_url,title=item.title;
    const box = el('div', `card-media${sensitive?' sensitive-media':''}`);
    const overlay=()=>{if(sensitive){const note=el('div','privacy-overlay');note.append(text('span',null,'sensitive_preview'));box.append(note);}};
    const placeholder = () => {
      const node = el('div', 'placeholder');
      node.append(text('span', null, 'no_photo')); box.replaceChildren(node);overlay();
    };
    if (imageURL) {
      const image = el('img'); image.src = imageURL; image.alt = sensitive?FinDIUI18n.t('sensitive_alt'):title || ''; image.loading = 'lazy';
      if(sensitive)image.dataset.sensitiveAlt='';
      image.addEventListener('error', placeholder, {once:true}); box.append(image);overlay();
    } else placeholder();
    return box;
  }
  function itemComparison(item, key) {
    const node = el('article', 'comparison-item');
    node.append(text('p', 'eyebrow', key), media(item), el('h3', null, item.title));
    const meta = el('p', 'card-meta');
    meta.dataset.itemMeta = JSON.stringify([item.category,item.color,item.brand,item.location,item.event_date]);
    meta.textContent = [item.category,item.color,item.brand,item.location].filter(Boolean).map(FinDIUI18n.label).join(' · ') + ' · ' + shortDate(item.event_date);
    node.append(meta);
    if (item.description) node.append(el('p', null, item.description));
    return node;
  }
  function score(value) { return value == null ? FinDIUI18n.t('not_recorded') : `${Math.round(Math.max(0, Math.min(1, Number(value) || 0)) * 100)}%`; }
  function threshold(value) { return value == null ? FinDIUI18n.t('not_recorded') : score(value); }
  function evidence(match) {
    const data = match.evidence;
    const mode = ['local','hybrid'].includes(data?.mode) ? data.mode : 'historical';
    const box = el('div', 'evidence'), head = el('div', 'evidence-head');
    head.append(text('h3', null, 'evidence'),text('span',`badge badge--${mode}`,`source_${mode}`));
    box.append(head,text('p','hint',`source_${mode}_note`));
    const rows = [['TEXT',match.text_sim,'text'],...(match.image_sim == null ? [] : [['IMAGE',match.image_sim,'image']]),['DETAILS',match.attr_score,'attributes']];
    rows.forEach(([key,value,weight]) => {
      const row = el('div','evidence-row'), label = text('span',null,key);
      const labelWrap = el('span');
      labelWrap.append(label);
      if (data?.weights?.[weight] != null) labelWrap.append(text('small',null,'weight',{count:Math.round(data.weights[weight]*100)}));
      const bar = el('div','bar'), fill = el('span'); fill.style.width = value==null?'0%':score(value); bar.append(fill);
      row.append(labelWrap,bar,el('strong',null,score(value))); box.append(row);
    });
    if (!data || mode === 'historical') return box;
    const lexical = data.text?.lexical, perceptual = data.image?.perceptual;
    if (lexical?.shared_terms?.length) {
      const clues = el('div','shared-clues'); clues.append(text('p','hint','shared_terms'));
      const terms = el('div','clue-stamps');
      lexical.shared_terms.forEach(term => {
        const node = el('span','clue',FinDIUI18n.label(term)); node.dataset.clueTerm=term; terms.append(node);
      });
      clues.append(terms); box.append(clues);
    }
    const details = el('details','signal-details'); details.append(text('summary',null,'detailed_signals'));
    function signals(key, values) {
      const group = el('div','signal-group'), list = el('dl','signal-list'); group.append(text('h4','meta',key));
      values.forEach(([key,value,weight]) => {
        const row = el('div'), label = text('dt',null,key);
        if (weight != null) label.append(text('small',null,'weight',{count:Math.round(weight*100)}));
        row.append(label,el('dd',null,value == null || weight === 0 ? FinDIUI18n.t('not_used') : score(value))); list.append(row);
      });
      group.append(list); details.append(group);
    }
    if (lexical) signals('local_text_signals',[
      ['jaccard',lexical.jaccard,lexical.weights?.jaccard],
      ['char_dice',lexical.char_dice,lexical.weights?.char_dice],
      ['containment',lexical.containment,lexical.weights?.containment]
    ]);
    if (data.text?.semantic != null) signals('text_blend',[
      ['local_text',data.text.local,data.text.weights.local],['semantic_text',data.text.semantic,data.text.weights.semantic]
    ]);
    if (perceptual) signals('local_image_signals',[
      ['dhash',perceptual.dhash_sim,perceptual.weights?.dhash],
      ['ahash',perceptual.ahash_sim,perceptual.weights?.ahash],
      ['colour_histogram',perceptual.histogram_sim,perceptual.weights?.histogram]
    ]);
    if (data.image?.semantic != null) signals('image_blend',[
      ['local_image',data.image.local,data.image.weights.local],['semantic_image',data.image.semantic,data.image.weights.semantic]
    ]);
    if (data.attributes) {
      signals('attribute_signals',['color','brand','location','date'].map(key=>[
        `signal_${key}`,data.attributes[key],data.attributes.weights?.[key]
      ]));
      details.append(text('p','hint','date_gap',{count:data.attributes.date_gap_days}));
      if (data.attributes.location === 0.5) details.append(text('p','hint','location_heuristic'));
    }
    details.append(text('p','hint','evidence_scope')); box.append(details);
    return box;
  }
  function shell() {
    const header = document.querySelector('[data-shell]');
    const skip = text('a','skip','skip'); skip.href = '#main';
    const brand = el('a','brand'); brand.href='index.html'; brand.setAttribute('aria-label','FinDIU');
    const mark=el('img','brand-mark');mark.src='favicon.svg';mark.alt='';
    const name=el('span','brand-name','FinDIU');name.append(text('span','brand-subtitle','brand'));brand.append(mark,name);
    const nav = el('nav','primary-nav'); nav.setAttribute('aria-label',FinDIUI18n.t('brand'));
    nav.append(link('dashboard','dashboard.html'),link('match_nav','dashboard.html#claims-heading'),link('new_report','report.html'));
    const actions=el('div','shell-actions');
    if (FinDIU.token()) {
      actions.append(link('new_report','report.html','button nav-report'));
      const account=el('details','account-menu');account.append(text('summary',null,'account'));const accountLinks=el('div','account-links');
      accountLinks.append(link('admin','admin.html'));
      const out = text('button','text-button','sign_out'); out.type='button';
      out.addEventListener('click',async () => {
        if (window.findiuDirty && !await confirm('unsaved')) return;
        window.findiuDirty = false; FinDIU.clearSession(); location.href='index.html';
      }); accountLinks.append(out);account.append(accountLinks);actions.append(account);
    } else actions.append(link('sign_in','auth.html','button'));
    const language = el('button','locale'); language.type='button'; language.dataset.localeToggle='';
    language.addEventListener('click',FinDIUI18n.toggle); actions.prepend(language);
    nav.querySelectorAll('a').forEach(a => { if (a.getAttribute('href') === location.pathname.split('/').pop()) a.setAttribute('aria-current','page'); });
    if(document.body.dataset.page==='match')nav.querySelector('a[href*=claims]').setAttribute('aria-current','page');
    const inner=el('div','shell-inner');inner.append(skip,brand,nav,actions);header.append(inner);
    const mobile=nav.cloneNode(true);mobile.className='mobile-nav';header.after(mobile);
    const footer = document.querySelector('[data-footer]');
    footer.append(text('span',null,'footer'),text('span','meta','brand'));
    const notification=el('div','toast'); notification.dataset.toast='';notification.setAttribute('role','status'); document.body.append(notification);
    const dialog=el('dialog');dialog.dataset.dialog='';dialog.setAttribute('aria-labelledby','dialog-title');dialog.setAttribute('aria-describedby','dialog-message');
    const heading=text('h2',null,'confirm');heading.id='dialog-title';
    const message=el('p');message.dataset.dialogMessage='';message.id='dialog-message';
    const form=el('form','actions');form.method='dialog';
    ['cancel','confirm'].forEach(key=>{const button=text('button',`button ${key==='cancel'?'button-light':''}`,key);button.value=key;form.append(button);});
    dialog.append(heading,message,form);document.body.append(dialog);
    FinDIUI18n.render();
  }
  window.FinDIUSession={require,el,text,link,shortDate,toast,confirm,formErrors,valid,skeleton,errorState,media,itemComparison,score,threshold,evidence};
  document.addEventListener('languagechange', () => {
    document.querySelectorAll('[data-item-meta]').forEach(node => {
      const values = JSON.parse(node.dataset.itemMeta), date = values.pop();
      node.textContent = values.filter(Boolean).map(FinDIUI18n.label).join(' · ') + ' · ' + shortDate(date);
    });
    document.querySelectorAll('[data-clue-term]').forEach(node => { node.textContent=FinDIUI18n.label(node.dataset.clueTerm); });
    document.querySelectorAll('[data-sensitive-alt]').forEach(node=>{node.alt=FinDIUI18n.t('sensitive_alt');});
  });
  document.addEventListener('DOMContentLoaded',shell);
})();
