(function () {
  if (!Api.hasToken()) {
    window.location.href = "login.html";
    return;
  }
  // Authorization is decided by the API (403), not by localStorage — a stale
  // or missing role shouldn't silently bounce an admin off this page.

  const name = localStorage.getItem("simuloschool_name");
  if (name) document.getElementById("user-name").textContent = name;

  document.getElementById("logout").addEventListener("click", () => {
    Api.clearToken();
    localStorage.removeItem("simuloschool_name");
    localStorage.removeItem("simuloschool_role");
    window.location.href = "login.html";
  });

  const STATUS_COPY = {
    uploaded: "Starting generation",
    processing: "Generating quiz",
    pending_review: "Awaiting your review",
    published: "Live for students",
    failed: "Generation failed",
  };

  // Statuses where work is actively in flight — these drive the live polling.
  const IN_FLIGHT = ["uploaded", "processing"];
  const POLL_MS = 4000;
  let pollTimer = null;

  const listEl = document.getElementById("pipeline");
  const listError = document.getElementById("list-error");

  // ---- upload ----
  const form = document.getElementById("upload-form");
  const uploadError = document.getElementById("upload-error");
  const uploadSuccess = document.getElementById("upload-success");
  const submitBtn = document.getElementById("upload-submit");

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    uploadError.hidden = true;
    uploadSuccess.hidden = true;

    const fileInput = document.getElementById("video");
    const body = new FormData();
    body.append("title", document.getElementById("title").value.trim());
    body.append("file", fileInput.files[0]);

    submitBtn.disabled = true;
    submitBtn.textContent = "Uploading…";
    try {
      await Api.upload("/admin/videos", body);
      // Upload and generation are separate outcomes: the file is safely stored
      // whatever the quiz step goes on to do.
      uploadSuccess.textContent =
        "Video stored. Quiz generation runs separately — track it below.";
      uploadSuccess.hidden = false;
      form.reset();
      loadPipeline();
    } catch (err) {
      uploadError.textContent = err.message || "Upload failed";
      uploadError.hidden = false;
    } finally {
      submitBtn.disabled = false;
      submitBtn.textContent = "Upload lesson";
    }
  });

  // ---- pipeline list ----
  function statusPill(status) {
    const pill = document.createElement("span");
    pill.className = "status-pill status-" + status;
    if (IN_FLIGHT.includes(status)) {
      const dot = document.createElement("span");
      dot.className = "pulse-dot";
      pill.appendChild(dot);
    }
    pill.appendChild(document.createTextNode(STATUS_COPY[status] || status));
    return pill;
  }

  function questionRow(question) {
    const li = document.createElement("li");
    li.className = "review-question";

    const head = document.createElement("p");
    head.className = "review-q-text";
    const tier = document.createElement("span");
    tier.className = "tier tier-" + question.difficulty;
    tier.textContent = question.difficulty;
    head.append(tier, document.createTextNode(" " + question.text));

    const opts = document.createElement("ol");
    opts.className = "review-options";
    question.options.forEach((option, idx) => {
      const optLi = document.createElement("li");
      optLi.textContent = option;
      if (idx === question.correct_idx) optLi.className = "correct";
      opts.appendChild(optLi);
    });

    li.append(head, opts);
    return li;
  }

  async function toggleReview(video, container, button) {
    if (container.dataset.loaded === "true") {
      container.hidden = !container.hidden;
      button.textContent = container.hidden ? "Review questions" : "Hide questions";
      return;
    }
    button.disabled = true;
    try {
      const questions = await Api.request(`/admin/videos/${video.id}/questions`);
      const list = document.createElement("ul");
      list.className = "review-list";
      questions.forEach((q) => list.appendChild(questionRow(q)));
      container.appendChild(list);
      container.dataset.loaded = "true";
      container.hidden = false;
      button.textContent = "Hide questions";
    } catch (err) {
      listError.textContent = err.message || "Could not load questions";
      listError.hidden = false;
    } finally {
      button.disabled = false;
    }
  }

  function videoCard(video) {
    const card = document.createElement("div");
    card.className = "report-card pipeline-card";

    const header = document.createElement("div");
    header.className = "pipeline-head";
    const title = document.createElement("h4");
    title.textContent = video.title;
    header.append(title, statusPill(video.status));

    const meta = document.createElement("p");
    meta.className = "video-meta";
    const bits = [new Date(video.created_at).toLocaleString()];
    if (IN_FLIGHT.includes(video.status)) {
      // Say which half of the pipeline is running, so a long wait is legible.
      bits.push(
        video.has_transcript
          ? "transcribed — writing questions now"
          : "transcribing the audio…"
      );
    } else {
      bits.push(video.question_count + " questions");
      if (video.has_transcript) bits.push("transcribed");
    }
    meta.textContent = bits.join(" · ");

    const actions = document.createElement("div");
    actions.className = "pipeline-actions";
    const review = document.createElement("div");
    review.hidden = true;

    if (video.question_count > 0) {
      const reviewBtn = document.createElement("button");
      reviewBtn.className = "btn btn-ghost";
      reviewBtn.textContent = "Review questions";
      reviewBtn.addEventListener("click", () => toggleReview(video, review, reviewBtn));
      actions.appendChild(reviewBtn);
    }

    if (video.status === "pending_review") {
      const publishBtn = document.createElement("button");
      publishBtn.className = "btn btn-primary";
      publishBtn.textContent = "Approve & publish";
      publishBtn.addEventListener("click", async () => {
        publishBtn.disabled = true;
        try {
          await Api.request(`/admin/videos/${video.id}/publish`, { method: "POST" });
          loadPipeline();
        } catch (err) {
          listError.textContent = err.message || "Could not publish";
          listError.hidden = false;
          publishBtn.disabled = false;
        }
      });
      actions.appendChild(publishBtn);
    }

    if (video.status === "failed" || video.status === "pending_review") {
      const retryBtn = document.createElement("button");
      retryBtn.className = "btn btn-ghost";
      retryBtn.textContent =
        video.status === "failed" ? "Retry generation" : "Regenerate quiz";
      retryBtn.title = "Reuses the stored video — no need to upload it again";
      retryBtn.addEventListener("click", async () => {
        retryBtn.disabled = true;
        try {
          await Api.request(`/admin/videos/${video.id}/retry`, { method: "POST" });
          loadPipeline();
        } catch (err) {
          listError.textContent = err.message || "Could not retry";
          listError.hidden = false;
          retryBtn.disabled = false;
        }
      });
      actions.appendChild(retryBtn);
    }

    const deleteBtn = document.createElement("button");
    deleteBtn.className = "btn btn-danger";
    deleteBtn.textContent = "Delete";
    deleteBtn.addEventListener("click", async () => {
      const warning =
        video.status === "published"
          ? `"${video.title}" is live for students. Delete it, its quiz, and the video file permanently?`
          : `Delete "${video.title}", its quiz, and the stored video file permanently?`;
      if (!window.confirm(warning)) return;
      deleteBtn.disabled = true;
      try {
        await Api.request(`/admin/videos/${video.id}`, { method: "DELETE" });
        loadPipeline();
      } catch (err) {
        listError.textContent = err.message || "Could not delete";
        listError.hidden = false;
        deleteBtn.disabled = false;
      }
    });
    actions.appendChild(deleteBtn);

    card.append(header, meta, actions, review);
    return card;
  }

  async function loadPipeline() {
    listError.hidden = true;
    try {
      const videos = await Api.request("/admin/videos");
      listEl.replaceChildren();
      if (videos.length === 0) {
        const empty = document.createElement("p");
        empty.className = "empty";
        empty.textContent = "No lessons uploaded yet.";
        listEl.appendChild(empty);
        return;
      }
      videos.forEach((video) => listEl.appendChild(videoCard(video)));

      // Keep refreshing while anything is still generating, then stop.
      clearTimeout(pollTimer);
      if (videos.some((v) => IN_FLIGHT.includes(v.status))) {
        pollTimer = setTimeout(loadPipeline, POLL_MS);
      }
    } catch (err) {
      listError.textContent =
        err.message === "Admin only"
          ? "This page is for admins. Sign in with an admin account to upload lessons."
          : err.message || "Could not load lessons";
      listError.hidden = false;
    }
  }

  loadPipeline();
})();
