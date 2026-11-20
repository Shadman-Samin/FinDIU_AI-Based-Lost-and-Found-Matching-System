(function () {
  const tokenKey = "findiu_access_token";

  function token() {
    return sessionStorage.getItem(tokenKey);
  }

  function clearSession() {
    sessionStorage.removeItem(tokenKey);
    sessionStorage.removeItem("findiu_user");
  }

  async function request(path, options = {}) {
    const headers = new Headers(options.headers || {});
    const accessToken = token();
    if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);
    if (!(options.body instanceof FormData) && options.body !== undefined) {
      headers.set("Content-Type", "application/json");
      options.body = JSON.stringify(options.body);
    }
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), options.timeout || 20000);
    try {
      const response = await fetch(`${window.FINDIU_CONFIG.apiBaseUrl}${path}`, {
        ...options, headers, signal: controller.signal
      });
      const data = await response.json().catch(() => ({}));
      if (response.status === 401) {
        const hadSession = Boolean(token());
        clearSession();
        if (hadSession && !location.pathname.endsWith("auth.html")) {
          const next = encodeURIComponent(location.pathname.split("/").pop() + location.search);
          location.replace(`auth.html?next=${next}`);
        }
      }
      if (!response.ok) {
        const error = new Error(data.error?.message || "Something went wrong.");
        error.status = response.status;
        error.payload = data;
        if (window.FinDIUI18n) error.message=FinDIUI18n.errorMessage(error);
        throw error;
      }
      return data;
    } finally {
      clearTimeout(timeout);
    }
  }

  window.FinDIU = { request, token, clearSession, tokenKey };
})();
