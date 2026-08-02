(function () {
  if (Api.hasToken()) {
    window.location.href = "index.html";
    return;
  }

  const form = document.getElementById("login-form");
  const errorEl = document.getElementById("login-error");
  const submitBtn = document.getElementById("login-submit");

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    errorEl.hidden = true;
    submitBtn.disabled = true;
    try {
      const data = await Api.request("/auth/login", {
        method: "POST",
        body: {
          email: document.getElementById("email").value.trim(),
          password: document.getElementById("password").value,
        },
      });
      Api.setToken(data.access_token);
      localStorage.setItem("simuloschool_name", data.name);
      localStorage.setItem("simuloschool_role", data.role);
      window.location.href = "index.html";
    } catch (err) {
      errorEl.textContent = err.message || "Login failed";
      errorEl.hidden = false;
    } finally {
      submitBtn.disabled = false;
    }
  });
})();
