document.addEventListener('DOMContentLoaded', () => {
  if (!FinDIUSession.require()) return;
  const {valid,formErrors,confirm,el,text} = FinDIUSession;
  const form = document.querySelector('[data-report-form]');
  const params = new URLSearchParams(location.search), editId = params.get('edit');
  const submit = form.querySelector('[type=submit]'), status = form.querySelector('[data-status]');
  const loadError = form.querySelector('[data-load-error]');
  const image = form.elements.image, preview = form.querySelector('[data-preview]'), remove = form.querySelector('[data-remove-image]');
  const consentCopy = form.querySelector('[data-i18n=consent]'), consentHelp = form.querySelector('[data-i18n=consent_help]');
  let metadata, revision, objectURL, originalImage, removeImage = false, ready = false;
  if (params.get('type') === 'found') form.elements.type.value = 'found';
  const dateInDhaka = (offset = 0) => {
    const now = new Date(Date.now() - offset * 86400000);
    const parts = new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Dhaka',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(now);
    return ['year','month','day'].map(type=>parts.find(part=>part.type===type).value).join('-');
  };
  form.elements.event_date.max = dateInDhaka();
  form.querySelectorAll('[data-date]').forEach(button => button.addEventListener('click', () => {
    form.elements.event_date.value = dateInDhaka(Number(button.dataset.date)); window.findiuDirty = true;
  }));
  const dirty = () => { if (ready) window.findiuDirty = true; };
  form.addEventListener('input',dirty); form.addEventListener('change',dirty);
  window.addEventListener('beforeunload',event => { if (window.findiuDirty) {event.preventDefault();event.returnValue='';} });
  document.addEventListener('click',async event => {
    const anchor = event.target.closest('a[href]');
    if (!anchor || !window.findiuDirty || anchor.hash === '#main' || event.ctrlKey || event.metaKey || anchor.target === '_blank') return;
    event.preventDefault();
    if (await confirm('unsaved')) {window.findiuDirty=false;location.href=anchor.href;}
  });
  function renderOptions() {
    if (!metadata) return;
    consentCopy.dataset.i18n = metadata.semantic_enabled ? 'consent_hybrid' : 'consent_local';
    consentHelp.dataset.i18n = metadata.semantic_enabled ? 'consent_help_hybrid' : 'consent_help_local';
    form.querySelectorAll('[data-vocab]').forEach(select => {
      const current = select.value;
      select.replaceChildren(new Option(FinDIUI18n.t('choose'),''),...metadata[select.dataset.vocab].map(option=>new Option(option[FinDIUI18n.locale],option.value)));
      select.value = current;
    });
    if (editId && revision) {
      const note = form.querySelector('[data-edit-notice]');note.hidden=false;
      note.textContent=FinDIUI18n.t('edit_notice',{count:revision});
      submit.dataset.i18n='save_changes';
    }
    FinDIUI18n.render(form);
  }
  document.addEventListener('languagechange',renderOptions);
  function clearObjectURL() { if (objectURL) {URL.revokeObjectURL(objectURL);objectURL=null;} }
  image.addEventListener('change', () => {
    clearObjectURL();
    const file=image.files[0];
    if (!file) {preview.src=originalImage || '';preview.hidden=!originalImage || removeImage;remove.hidden=preview.hidden;return;}
    if (!['image/jpeg','image/png'].includes(file.type) || file.size>5*1024*1024) {
      image.value='';status.dataset.i18n='image_invalid';FinDIUI18n.render(form);
      preview.src=originalImage || '';preview.hidden=!originalImage || removeImage;remove.hidden=preview.hidden;return;
    }
    status.removeAttribute('data-i18n');status.textContent='';removeImage=false;
    objectURL=URL.createObjectURL(file);preview.src=objectURL;preview.hidden=false;remove.hidden=false;
  });
  remove.addEventListener('click', () => {
    clearObjectURL();image.value='';preview.removeAttribute('src');preview.hidden=true;remove.hidden=true;removeImage=Boolean(originalImage);dirty();
  });
  window.addEventListener('pagehide',clearObjectURL);
  async function load() {
    submit.disabled=true;form.setAttribute('aria-busy','true');loadError.replaceChildren();
    try {
      const [meta,item] = await Promise.all([FinDIU.request('/api/v1/metadata'),editId?FinDIU.request(`/api/v1/items/${encodeURIComponent(editId)}`):Promise.resolve(null)]);
      metadata=meta;renderOptions();
      if (item) {
        revision=item.revision;
        for (const name of ['type','category','color','brand','title','description','location','event_date','private_detail']) form.elements.namedItem(name).value=item[name] || '';
        form.elements.type.disabled=true;
        originalImage=item.image_url;
        if (originalImage) {preview.src=originalImage;preview.hidden=false;remove.hidden=false;}
        if (item.status!=='active') throw {status:409,payload:{error:{code:'lifecycle_conflict'}}};
      }
      ready=true;renderOptions();submit.disabled=false;
    } catch(error) {
      loadError.append(el('p',null,FinDIUI18n.errorMessage(error)));
      const retry=text('button','text-button','retry');retry.type='button';retry.addEventListener('click',load);loadError.append(retry);
    } finally {form.removeAttribute('aria-busy');}
  }
  form.addEventListener('submit',async event => {
    event.preventDefault();if (!ready || !valid(form)) return;
    submit.disabled=true;status.dataset.i18n='saving';FinDIUI18n.render(form);
    const body=new FormData(form);body.delete('type');
    body.set('semantic_consent',String(Boolean(metadata.semantic_enabled && form.elements.consent.checked)));
    if (!image.files.length) body.delete('image');
    if (editId) {body.set('expected_revision',revision);if(removeImage)body.set('remove_image','true');}
    try {
      await FinDIU.request(editId?`/api/v1/items/${encodeURIComponent(editId)}`:`/api/v1/items?type=${encodeURIComponent(form.elements.type.value)}`,{method:editId?'PATCH':'POST',body,timeout:30000});
      window.findiuDirty=false;location.href='dashboard.html?created=1';
    } catch(error) {status.removeAttribute('data-i18n');formErrors(form,error);submit.disabled=false;}
  });
  load();
});
