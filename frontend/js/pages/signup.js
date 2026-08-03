(function () {
  if (Api.hasToken()) {
    window.location.href = "index.html";
    return;
  }

  const form = document.getElementById("signup-form");
  const errorEl = document.getElementById("signup-error");
  const submitBtn = document.getElementById("signup-submit");

  function showError(message) {
    errorEl.textContent = message;
    errorEl.hidden = false;
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    errorEl.hidden = true;

    const password = document.getElementById("password").value;
    if (password.length < 8) {
      showError("Password must be at least 8 characters.");
      return;
    }

    const parentEmail = document.getElementById("parent-email").value.trim();
    const body = {
      name: document.getElementById("name").value.trim(),
      email: document.getElementById("email").value.trim(),
      password,
    };
    // Send the field only when filled — the API rejects an empty string as an
    // invalid address, but accepts it being absent.
    if (parentEmail) body.parent_email = parentEmail;

    submitBtn.disabled = true;
    submitBtn.textContent = "Creating account…";
    try {
      const data = await Api.request("/auth/signup", { method: "POST", body });
      Api.setToken(data.access_token);
      localStorage.setItem("simuloschool_name", data.name);
      localStorage.setItem("simuloschool_role", data.role);
      window.location.href = "lessons.html";
    } catch (err) {
      showError(err.message || "Could not create your account");
    } finally {
      submitBtn.disabled = false;
      submitBtn.textContent = "Create account";
    }
  });
})();
