(function () {
  if (!Api.hasToken()) {
    window.location.href = "login.html";
    return;
  }

  const userNameEl = document.getElementById("user-name");
  const name = localStorage.getItem("simuloschool_name");
  if (name) userNameEl.textContent = name;

  // The API is the source of truth for role — Upload stays hidden unless it
  // confirms this user is an admin.
  Api.request("/auth/me")
    .then((user) => {
      localStorage.setItem("simuloschool_role", user.role);
      const uploadLink = document.getElementById("admin-link");
      if (uploadLink && user.role === "admin") uploadLink.hidden = false;
    })
    .catch(() => {});

  document.getElementById("logout").addEventListener("click", () => {
    Api.clearToken();
    localStorage.removeItem("simuloschool_name");
    localStorage.removeItem("simuloschool_role");
    window.location.href = "login.html";
  });

  const listEl = document.getElementById("video-list");
  const emptyEl = document.getElementById("empty-state");
  const errorEl = document.getElementById("list-error");

  async function loadVideos() {
    try {
      const videos = await Api.request("/videos");
      if (videos.length === 0) {
        emptyEl.hidden = false;
        return;
      }
      for (const video of videos) {
        const li = document.createElement("li");
        li.className = "report-card sim-card";

        const thumb = document.createElement("div");
        thumb.className = "sim-thumb";
        const gridLines = document.createElement("div");
        gridLines.className = "grid-lines";
        const play = document.createElement("div");
        play.className = "mini-play";
        play.textContent = "▶";
        thumb.append(gridLines, play);

        const body = document.createElement("div");
        body.className = "sim-body";
        const subj = document.createElement("div");
        subj.className = "subj";
        subj.textContent = "Lesson";
        const title = document.createElement("h3");
        title.textContent = video.title;
        const meta = document.createElement("p");
        meta.className = "video-meta";
        meta.textContent = new Date(video.created_at).toLocaleDateString();
        body.append(subj, title, meta);

        li.append(thumb, body);
        listEl.appendChild(li);
      }
    } catch (err) {
      errorEl.textContent = err.message || "Could not load videos";
      errorEl.hidden = false;
    }
  }

  loadVideos();
})();
