// Marketing pages (sample report / sample dashboard) show a single nav CTA.
// Logged out it is "Login"; logged in that is wrong — the visitor already has
// an account, so the CTA becomes the way back into the app.
//
// Token presence is read from localStorage only. No /auth/me call: these pages
// show nothing user-specific, so a stale token costs a redirect to login at
// worst, and a network round trip would delay the nav on every page load.
(function () {
  if (typeof Api === "undefined" || !Api.hasToken()) return;

  const cta = document.getElementById("nav-cta");
  if (!cta) return;

  cta.textContent = "My Lessons";
  cta.href = "lessons.html";
})();
