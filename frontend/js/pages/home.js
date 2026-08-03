// Landing page auth state: show Login when logged out; when logged in, show
// the banner + user name and swap the CTA to the lessons page.
(function () {
  const authCta = document.getElementById("auth-cta");
  const logoutBtn = document.getElementById("logout");
  const navUser = document.getElementById("nav-user");
  const banner = document.getElementById("login-banner");
  const bannerName = document.getElementById("banner-name");
  const heroCta = document.getElementById("hero-cta");
  const demoCta = document.getElementById("demo-cta");

  if (Api.hasToken()) {
    const name = localStorage.getItem("simuloschool_name") || "there";

    banner.hidden = false;
    bannerName.textContent = name;

    // Ask the API who this token belongs to — a role cached in localStorage can
    // be stale or missing (different origin, older login, cleared storage).
    Api.request("/auth/me")
      .then((user) => {
        localStorage.setItem("simuloschool_name", user.name);
        localStorage.setItem("simuloschool_role", user.role);
        navUser.textContent = "Hi, " + user.name;
        bannerName.textContent = user.name;
        // Upload is admin-only — reveal it only once the server confirms the
        // role. Students and logged-out visitors never see it.
        if (user.role === "admin") {
          ["admin-link", "admin-nav-link", "banner-admin"].forEach((id) => {
            const el = document.getElementById(id);
            if (el) el.hidden = false;
          });
        }
      })
      .catch(() => {
        /* offline or expired — the nav still works, just without admin links */
      });

    navUser.textContent = "Hi, " + name;
    navUser.style.display = "inline";

    // Logged in: the signup CTA becomes the way back into the app, and the
    // separate Login link is redundant.
    authCta.textContent = "My Lessons";
    authCta.href = "lessons.html";
    const loginLink = document.getElementById("login-link");
    if (loginLink) loginLink.hidden = true;

    logoutBtn.style.display = "inline-block";
    logoutBtn.addEventListener("click", () => {
      Api.clearToken();
      localStorage.removeItem("simuloschool_name");
      localStorage.removeItem("simuloschool_role");
      window.location.reload();
    });

    heroCta.textContent = "▶ Continue learning";
    heroCta.href = "lessons.html";

    // Logged out this points at signup; logged in it went to login.html, which
    // bounced the visitor through sign-in and straight back to where they were.
    if (demoCta) {
      demoCta.textContent = "▶ Continue learning";
      demoCta.href = "lessons.html";
    }
  }
})();
