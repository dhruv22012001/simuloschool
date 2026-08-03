// Single API helper: base URL from config.js, JWT in memory + localStorage,
// Authorization header attached to every request.
(function () {
  const TOKEN_KEY = "simuloschool_token";
  let token = localStorage.getItem(TOKEN_KEY);

  // fetch() rejects with a bare "Failed to fetch" for a DNS miss, a blocked
  // CORS preflight and a dead server alike — the one message a user cannot act
  // on and a developer cannot tell apart. Name the host being called so the
  // failure points back at the configuration that caused it.
  async function send(path, init) {
    const base = window.API_BASE_URL;
    if (!base) {
      throw new Error(
        "API is not configured: window.API_BASE_URL is unset. js/config.js is missing or empty."
      );
    }
    try {
      return await fetch(base + path, init);
    } catch (_) {
      throw new Error(
        "Cannot reach the API at " +
          base +
          ". The host may be unreachable, asleep, or blocking this origin via CORS."
      );
    }
  }

  // Both callers surface the API's own `detail` when there is one, and fall
  // back to the status text for error pages that are not our JSON.
  async function errorFrom(resp) {
    let detail = resp.statusText;
    try {
      const data = await resp.json();
      if (data.detail) detail = data.detail;
    } catch (_) {
      /* non-JSON error body */
    }
    return new Error(detail);
  }

  async function request(path, options = {}) {
    const headers = { ...(options.headers || {}) };
    if (options.body !== undefined) headers["Content-Type"] = "application/json";
    if (token) headers["Authorization"] = "Bearer " + token;

    const resp = await send(path, {
      method: options.method || "GET",
      headers,
      body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
    });

    if (resp.status === 401 && !path.startsWith("/auth/")) {
      clearToken();
      window.location.href = "login.html";
      throw new Error("Session expired");
    }
    if (!resp.ok) throw await errorFrom(resp);
    return resp.status === 204 ? null : resp.json();
  }

  // Multipart upload — the browser must set its own Content-Type boundary,
  // so this path deliberately skips the JSON header request() adds.
  async function upload(path, formData) {
    const headers = {};
    if (token) headers["Authorization"] = "Bearer " + token;

    const resp = await send(path, {
      method: "POST",
      headers,
      body: formData,
    });

    if (resp.status === 401) {
      clearToken();
      window.location.href = "login.html";
      throw new Error("Session expired");
    }
    if (!resp.ok) throw await errorFrom(resp);
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
