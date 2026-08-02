// Single API helper: base URL from config.js, JWT in memory + localStorage,
// Authorization header attached to every request.
(function () {
  const TOKEN_KEY = "simuloschool_token";
  let token = localStorage.getItem(TOKEN_KEY);

  async function request(path, options = {}) {
    const headers = { ...(options.headers || {}) };
    if (options.body !== undefined) headers["Content-Type"] = "application/json";
    if (token) headers["Authorization"] = "Bearer " + token;

    const resp = await fetch(window.API_BASE_URL + path, {
      method: options.method || "GET",
      headers,
      body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
    });

    if (resp.status === 401 && !path.startsWith("/auth/")) {
      clearToken();
      window.location.href = "login.html";
      throw new Error("Session expired");
    }
    if (!resp.ok) {
      let detail = resp.statusText;
      try {
        const data = await resp.json();
        if (data.detail) detail = data.detail;
      } catch (_) {
        /* non-JSON error body */
      }
      throw new Error(detail);
    }
    return resp.status === 204 ? null : resp.json();
  }

  // Multipart upload — the browser must set its own Content-Type boundary,
  // so this path deliberately skips the JSON header request() adds.
  async function upload(path, formData) {
    const headers = {};
    if (token) headers["Authorization"] = "Bearer " + token;

    const resp = await fetch(window.API_BASE_URL + path, {
      method: "POST",
      headers,
      body: formData,
    });

    if (resp.status === 401) {
      clearToken();
      window.location.href = "login.html";
      throw new Error("Session expired");
    }
    if (!resp.ok) {
      let detail = resp.statusText;
      try {
        const data = await resp.json();
        if (data.detail) detail = data.detail;
      } catch (_) {
        /* non-JSON error body */
      }
      throw new Error(detail);
    }
    return resp.json();
  }

  function setToken(t) {
    token = t;
    localStorage.setItem(TOKEN_KEY, t);
  }

  function clearToken() {
    token = null;
    localStorage.removeItem(TOKEN_KEY);
  }

  window.Api = {
    request,
    upload,
    setToken,
    clearToken,
    hasToken: () => Boolean(token),
  };
})();
