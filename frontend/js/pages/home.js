// Landing page auth state: show Login when logged out; when logged in, show
// the banner + user name and swap the CTA to the lessons page.
(function () {
  const authCta = document.getElementById("auth-cta");
  const logoutBtn = document.getElementById("logout");
  const navUser = document.getElementById("nav-user");
  const banner = document.getElementById("login-banner");
  const bannerName = document.getElementById("banner-name");
  const heroCta = document.getElementById("hero-cta");

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
        if (user.role === "admin") {
          document.getElementById("banner-admin").hidden = false;
        }
      })
      .catch(() => {
        /* offline or expired — the nav still works, just without admin links */
      });

    navUser.textContent = "Hi, " + name;
    navUser.style.display = "inline";

    authCta.textContent = "My Lessons";
    authCta.href = "lessons.html";

    logoutBtn.style.display = "inline-block";
    logoutBtn.addEventListener("click", () => {
      Api.clearToken();
      localStorage.removeItem("simuloschool_name");
      localStorage.removeItem("simuloschool_role");
      window.location.reload();
    });

    heroCta.textContent = "▶ Continue learning";
    heroCta.href = "lessons.html";
  }
})();
