document.addEventListener('DOMContentLoaded', () => {
  const form = document.querySelector('[data-auth]');
  const {valid,formErrors} = FinDIUSession;
  const message = form.querySelector('[data-status]');
  const button = form.querySelector('[type=submit]');
  const next = new URLSearchParams(location.search).get('next');
  // Only known local destinations may receive a post-login redirect.
  const safeNext = next && /^(index|dashboard|report|match|admin)\.html(?:\?[^#\\\r\n]*)?$/.test(next) ? next : 'dashboard.html';
  const switchLink = document.querySelector('[data-auth-switch]');
  if (next) switchLink.href += `?next=${encodeURIComponent(safeNext)}`;
  const visibility = document.querySelector('[data-password]');
  visibility.addEventListener('click', () => {
    const input = form.elements.password;
    const shown = input.type === 'password'; input.type = shown ? 'text' : 'password';
    visibility.setAttribute('aria-pressed',String(shown));
    visibility.dataset.i18n = shown ? 'hide' : 'show'; FinDIUI18n.render(form);
  });
  if (new URLSearchParams(location.search).has('registered')) { message.dataset.i18n = 'registered'; FinDIUI18n.render(form); }
  form.addEventListener('submit', async event => {
    event.preventDefault();
    if (!valid(form)) return;
    message.removeAttribute('data-i18n'); message.textContent = '';
    button.disabled = true;
    button.dataset.i18n = 'sending'; FinDIUI18n.render(form);
    const values = Object.fromEntries(new FormData(form));
    values.email = values.email.trim();
    let registered = false;
    try {
      if (form.dataset.auth === 'register') {
        await FinDIU.request('/api/v1/auth/register',{method:'POST',body:{...values,name:values.name.trim(),locale:FinDIUI18n.locale}});
        registered = true;
      }
      const result = await FinDIU.request('/api/v1/auth/login',{method:'POST',body:{email:values.email,password:values.password}});
      sessionStorage.setItem(FinDIU.tokenKey,result.access_token);
      location.href = safeNext;
    } catch (error) {
      if (registered) {
        location.href = `auth.html?registered=1&next=${encodeURIComponent(safeNext)}`;
        return;
      }
      if (error.payload?.error?.code === 'email_in_use') error.payload.error.fields = [{field:'email'}];
      formErrors(form,error);
    } finally {
      button.disabled = false; button.dataset.i18n = form.dataset.auth === 'register' ? 'create_account' : 'sign_in'; FinDIUI18n.render(form);
    }
  });
});
