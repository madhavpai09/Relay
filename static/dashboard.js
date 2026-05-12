const AUTO_REFRESH_MS = 4000;

const state = {
  jobs: [],
  selectedJobId: null,
  autoRefreshId: null,
};

const elements = {
  flashMessage: document.getElementById("flashMessage"),
  heroHealthStatus: document.getElementById("heroHealthStatus"),
  heroRepositoryCount: document.getElementById("heroRepositoryCount"),
  heroVerifiedRepositoryCount: document.getElementById("heroVerifiedRepositoryCount"),
  heroJobCount: document.getElementById("heroJobCount"),
  heroWorkerCount: document.getElementById("heroWorkerCount"),
  heroQueuedJobCount: document.getElementById("heroQueuedJobCount"),
  autoRefreshLabel: document.getElementById("autoRefreshLabel"),
  repositoriesGrid: document.getElementById("repositoriesGrid"),
  queueSummaryGrid: document.getElementById("queueSummaryGrid"),
  queuedJobsList: document.getElementById("queuedJobsList"),
  activeJobsList: document.getElementById("activeJobsList"),
  currentJobsList: document.getElementById("currentJobsList"),
  processedJobsList: document.getElementById("processedJobsList"),
  workersGrid: document.getElementById("workersGrid"),
  jobLogsViewer: document.getElementById("jobLogsViewer"),
  selectedJobMeta: document.getElementById("selectedJobMeta"),
  simulationStatusCard: document.getElementById("simulationStatusCard"),
  repositoryForm: document.getElementById("repositoryForm"),
  resetRepositoryFormButton: document.getElementById("resetRepositoryFormButton"),
};

function escapeHtml(value) {
  return String(value ?? "—")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function showFlash(message, isError = false) {
  const flash = elements.flashMessage;
  if (!flash) return;
  flash.textContent = message;
  flash.hidden = false;
  flash.classList.toggle("error", isError);
  clearTimeout(showFlash.timeoutId);
  showFlash.timeoutId = window.setTimeout(() => {
    flash.hidden = true;
  }, 3600);
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, options);
  const data = await response.json().catch(() => ({}));

  if (!response.ok) {
    const detail = data.detail || data.message || `Request failed with status ${response.status}`;
    throw new Error(detail);
  }

  return data;
}

function formatValue(value) {
  return value ?? "—";
}

function formatDateTime(value) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

function statusPill(status) {
  const normalized = String(status || "").toLowerCase();
  let extraClass = "";
  if (["processed", "sent", "active", "online", "verified"].includes(normalized)) extraClass = "success";
  if (["in_queue", "assigned", "processing", "busy", "unverified"].includes(normalized)) extraClass = "warning";
  if (["failed", "offline", "error", "deleted"].includes(normalized)) extraClass = "error";
  return `<span class="meta-pill ${extraClass}">${escapeHtml(status)}</span>`;
}

function renderEmpty(target, message) {
  target.innerHTML = `<div class="empty-state">${escapeHtml(message)}</div>`;
}

function renderQueueSummary(summary = {}) {
  const cards = [
    { label: "Queued Jobs", value: summary.queuedCount ?? 0 },
    { label: "Active Jobs", value: summary.activeCount ?? 0 },
    { label: "Workers Online", value: summary.workerCount ?? 0 },
    { label: "Busy Workers", value: summary.busyWorkerCount ?? 0 },
  ];

  elements.queueSummaryGrid.innerHTML = cards
    .map(
      (card) => `
        <article class="summary-card">
          <span class="metric-label">${escapeHtml(card.label)}</span>
          <strong>${escapeHtml(card.value)}</strong>
        </article>
      `,
    )
    .join("");
}

async function loadHealth() {
  try {
    const health = await fetchJson("/health");
    if (elements.heroHealthStatus) {
      elements.heroHealthStatus.textContent = `${health.status} / ${health.service}`;
    }
  } catch (error) {
    if (elements.heroHealthStatus) {
      elements.heroHealthStatus.textContent = "Unavailable";
    }
    throw error;
  }
}

function repositoryActionLabel(repo) {
  return repo.verified ? "Re-Verify" : "Verify Repository";
}

function renderRepositories(repositories) {
  if (elements.heroRepositoryCount) {
    elements.heroRepositoryCount.textContent = String(repositories.length);
  }
  if (elements.heroVerifiedRepositoryCount) {
    elements.heroVerifiedRepositoryCount.textContent = String(
      repositories.filter((repo) => repo.verified).length,
    );
  }

  if (!repositories.length) {
    renderEmpty(elements.repositoriesGrid, "No repositories registered yet.");
    return;
  }

  elements.repositoriesGrid.innerHTML = repositories
    .map(
      (repo) => `
        <article class="repo-card">
          <div class="card-topline">
            <div>
              <h4>${escapeHtml(repo.fullName)}</h4>
              <p class="card-subtitle">${escapeHtml(repo.provider)} • ${escapeHtml(repo.language)}</p>
            </div>
            <div class="meta-pill-row">
              ${statusPill(repo.active ? "active" : "inactive")}
              ${statusPill(repo.verified ? "verified" : "unverified")}
            </div>
          </div>
          <div class="repo-meta">
            <span class="meta-line"><strong>Branch:</strong> ${escapeHtml(repo.defaultBranch)}</span>
            <span class="meta-line"><strong>Tracked:</strong> ${escapeHtml((repo.trackedBranches || []).join(", "))}</span>
            <span class="meta-line"><strong>Pipeline:</strong> ${escapeHtml(repo.pipelineFile)}</span>
            <span class="meta-line"><strong>Path:</strong> ${escapeHtml(repo.localPath)}</span>
            <span class="meta-line"><strong>Last Verified:</strong> ${escapeHtml(formatDateTime(repo.verifiedAt))}</span>
          </div>
          <div class="repo-validation-result">
            ${escapeHtml(repo.verificationMessage || "Verification status not checked yet.")}
          </div>
          <div class="repo-actions">
            <button class="repo-action secondary-button" data-verify-repo="${escapeHtml(repo.id)}">${repositoryActionLabel(repo)}</button>
            <button class="repo-action secondary-button" data-unverify-repo="${escapeHtml(repo.id)}" ${repo.verified ? "" : "disabled"}>Clear Verification</button>
            <button class="repo-action danger-button" data-delete-repo="${escapeHtml(repo.id)}">Delete</button>
          </div>
        </article>
      `,
    )
    .join("");

  document.querySelectorAll("[data-verify-repo]").forEach((button) => {
    button.addEventListener("click", async () => {
      const repoId = button.getAttribute("data-verify-repo");
      try {
        const result = await fetchJson(`/repositories/${repoId}/validate`, { method: "POST" });
        showFlash(`Repository ${result.repository.fullName} verified successfully.`);
        await Promise.all([loadRepositories(), loadQueue()]);
      } catch (error) {
        showFlash(error.message, true);
      }
    });
  });

  document.querySelectorAll("[data-unverify-repo]").forEach((button) => {
    button.addEventListener("click", async () => {
      const repoId = button.getAttribute("data-unverify-repo");
      try {
        const result = await fetchJson(`/repositories/${repoId}/unverify`, { method: "POST" });
        showFlash(`${result.repository.fullName} is now marked unverified.`);
        await loadRepositories();
      } catch (error) {
        showFlash(error.message, true);
      }
    });
  });

  document.querySelectorAll("[data-delete-repo]").forEach((button) => {
    button.addEventListener("click", async () => {
      const repoId = button.getAttribute("data-delete-repo");
      if (!window.confirm("Delete this repository from the Relay master?")) {
        return;
      }
      try {
        const result = await fetchJson(`/repositories/${repoId}`, { method: "DELETE" });
        showFlash(`${result.repository.fullName} deleted from Relay.`);
        await Promise.all([loadRepositories(), loadQueue(), loadSimulationStatus()]);
      } catch (error) {
        showFlash(error.message, true);
      }
    });
  });
}

async function loadRepositories() {
  const data = await fetchJson("/repositories");
  renderRepositories(data.repositories);
  return data.repositories;
}

async function loadQueue() {
  const data = await fetchJson("/queue");
  if (elements.heroQueuedJobCount) {
    elements.heroQueuedJobCount.textContent = String(data.summary?.queuedCount ?? data.queuedJobs.length);
  }
  renderQueueSummary(data.summary);

  if (!data.queuedJobs.length) {
    renderEmpty(elements.queuedJobsList, "No jobs are waiting in the queue.");
  } else {
    elements.queuedJobsList.innerHTML = data.queuedJobs
      .map(
        (job) => `
          <article class="queue-item">
            <div class="card-topline">
              <h4>${escapeHtml(job.repository || "Unknown repository")}</h4>
              ${statusPill("in_queue")}
            </div>
            <div class="job-meta">
              <span class="meta-line"><strong>Job:</strong> ${escapeHtml(job.id)}</span>
              <span class="meta-line"><strong>Trigger:</strong> ${escapeHtml(job.triggerType)}</span>
              <span class="meta-line"><strong>Language:</strong> ${escapeHtml(job.language)}</span>
              <span class="meta-line"><strong>Priority:</strong> ${escapeHtml(job.priorityLabel)} (${escapeHtml(job.priorityScore)})</span>
              <span class="meta-line"><strong>Ref:</strong> ${escapeHtml(formatValue(job.ref))}</span>
              <span class="meta-line"><strong>Reason:</strong> ${escapeHtml(job.priorityReason)}</span>
              <span class="meta-line"><strong>Queued:</strong> ${escapeHtml(formatDateTime(job.createdAt))}</span>
            </div>
          </article>
        `,
      )
      .join("");
  }

  if (!data.activeJobs.length) {
    renderEmpty(elements.activeJobsList, "No jobs are currently assigned or processing.");
  } else {
    elements.activeJobsList.innerHTML = data.activeJobs
      .map(
        (job) => `
          <article class="queue-item">
            <div class="card-topline">
              <h4>${escapeHtml(job.repository || "Unknown repository")}</h4>
              ${statusPill(job.status)}
            </div>
            <div class="job-meta">
              <span class="meta-line"><strong>Job:</strong> ${escapeHtml(job.id)}</span>
              <span class="meta-line"><strong>Worker:</strong> ${escapeHtml(formatValue(job.assignedWorkerName))}</span>
              <span class="meta-line"><strong>Language:</strong> ${escapeHtml(job.language)}</span>
              <span class="meta-line"><strong>Priority:</strong> ${escapeHtml(job.priorityLabel)} (${escapeHtml(job.priorityScore)})</span>
              <span class="meta-line"><strong>Started:</strong> ${escapeHtml(formatDateTime(job.startedAt))}</span>
            </div>
          </article>
        `,
      )
      .join("");
  }

  return data;
}

async function loadJobs() {
  const data = await fetchJson("/jobs");
  state.jobs = data.jobs;
  if (elements.heroJobCount) {
    elements.heroJobCount.textContent = String(data.jobs.length);
  }

  if (!data.jobs.length) {
    renderEmpty(elements.currentJobsList, "No current jobs.");
    renderEmpty(elements.processedJobsList, "No processed jobs yet.");
    elements.jobLogsViewer.textContent = "No job selected.";
    elements.selectedJobMeta.textContent = "Select a job to inspect logs";
    state.selectedJobId = null;
    return data.jobs;
  }

  if (!state.selectedJobId || !data.jobs.some((job) => job.id === state.selectedJobId)) {
    state.selectedJobId = data.jobs[0].id;
  }

  const currentStatuses = new Set(["received", "in_queue", "assigned", "processing"]);
  const currentJobs = data.jobs.filter((job) => currentStatuses.has(job.status));
  const processedJobs = data.jobs.filter((job) => !currentStatuses.has(job.status));

  function renderJobList(target, jobs, emptyMessage) {
    if (!jobs.length) {
      renderEmpty(target, emptyMessage);
      return;
    }

    target.innerHTML = jobs
      .map(
        (job) => `
          <article class="job-item ${job.id === state.selectedJobId ? "selected" : ""}">
            <div class="card-topline">
              <div>
                <h4>${escapeHtml(job.repository || "Unknown repository")}</h4>
                <p class="card-subtitle">${escapeHtml(job.triggerType)} • ${escapeHtml(job.language)}</p>
              </div>
              ${statusPill(job.status)}
            </div>
            <div class="job-meta">
              <span class="meta-line"><strong>Job:</strong> ${escapeHtml(job.id)}</span>
              <span class="meta-line"><strong>Worker:</strong> ${escapeHtml(formatValue(job.assignedWorkerName))}</span>
              <span class="meta-line"><strong>Commit:</strong> ${escapeHtml(formatValue(job.commitSha))}</span>
              <span class="meta-line"><strong>Priority:</strong> ${escapeHtml(job.priorityLabel)} (${escapeHtml(job.priorityScore)})</span>
              <span class="meta-line"><strong>Created:</strong> ${escapeHtml(formatDateTime(job.createdAt))}</span>
            </div>
            <div class="meta-pill-row">
              <button class="job-log-button" data-job-logs="${escapeHtml(job.id)}">View Logs</button>
            </div>
          </article>
        `,
      )
      .join("");
  }

  renderJobList(elements.currentJobsList, currentJobs, "No current jobs.");
  renderJobList(elements.processedJobsList, processedJobs, "No processed jobs yet.");

  document.querySelectorAll("[data-job-logs]").forEach((button) => {
    button.addEventListener("click", async () => {
      const jobId = button.getAttribute("data-job-logs");
      await selectJob(jobId);
      await loadJobs();
    });
  });

  if (state.selectedJobId) {
    await selectJob(state.selectedJobId);
  }

  return data.jobs;
}

async function selectJob(jobId) {
  state.selectedJobId = jobId;
  const job = state.jobs.find((item) => item.id === jobId);
  if (!job) {
    elements.jobLogsViewer.textContent = "Selected job not found.";
    return;
  }

  elements.selectedJobMeta.textContent = `${job.repository || "Unknown repository"} • ${job.status} • ${job.language}`;
  const data = await fetchJson(`/jobs/${jobId}/logs`);
  const logLines = data.logs.length
    ? data.logs.map((log) => `[${log.timestamp}] ${log.level.toUpperCase()}  ${log.message}`).join("\n")
    : "No logs available for this job yet.";
  elements.jobLogsViewer.textContent = logLines;
}

async function loadWorkers() {
  const data = await fetchJson("/workers");
  if (elements.heroWorkerCount) {
    elements.heroWorkerCount.textContent = String(data.workers.length);
  }

  if (!data.workers.length) {
    renderEmpty(elements.workersGrid, "No workers are configured.");
    return data.workers;
  }

  elements.workersGrid.innerHTML = data.workers
    .map(
      (worker) => `
        <article class="worker-card">
          <div class="card-topline">
            <div>
              <h4>${escapeHtml(worker.name)}</h4>
              <p class="card-subtitle">${escapeHtml(worker.id)}</p>
            </div>
            ${statusPill(worker.currentJobId ? "busy" : "online")}
          </div>
          <div class="worker-meta">
            <span class="meta-line"><strong>Supports:</strong> ${escapeHtml(worker.supportedLanguages.join(", "))}</span>
            <span class="meta-line"><strong>Current Job:</strong> ${escapeHtml(formatValue(worker.currentJobId))}</span>
            <span class="meta-line"><strong>Jobs Completed:</strong> ${escapeHtml(worker.jobsCompleted)}</span>
            <span class="meta-line"><strong>Last Assigned:</strong> ${escapeHtml(formatDateTime(worker.lastAssignedAt))}</span>
          </div>
        </article>
      `,
    )
    .join("");

  return data.workers;
}

async function loadSimulationStatus() {
  const data = await fetchJson("/simulation");
  const coverage = data.coverage || {};
  const coverageRepos = (coverage.repositories || [])
    .map((repo) => `${repo.fullName}: ${(repo.trackedBranches || []).join(", ")}`)
    .join(" | ");
  elements.simulationStatusCard.innerHTML = `
    <p><strong>Running:</strong> ${escapeHtml(data.running ? "Yes" : "No")}</p>
    <p><strong>Min Delay:</strong> ${escapeHtml(data.minDelaySeconds)}s</p>
    <p><strong>Max Delay:</strong> ${escapeHtml(data.maxDelaySeconds)}s</p>
    <p><strong>Coverage Ready:</strong> ${escapeHtml(coverage.meetsMinimum ? "Yes" : "No")}</p>
    <p><strong>Eligible Repositories:</strong> ${escapeHtml(coverage.eligibleRepositoryCount ?? 0)} / ${escapeHtml(coverage.requiredRepositoryCount ?? 3)}</p>
    <p><strong>Tracked Branches:</strong> ${escapeHtml(coverage.coveredBranchCount ?? 0)} / ${escapeHtml(coverage.requiredBranchCount ?? 6)}</p>
    <p><strong>Readiness Detail:</strong> ${escapeHtml(data.readinessReason || "Simulation can cover the minimum finals scenario.")}</p>
    <p><strong>Coverage Plan:</strong> ${escapeHtml(coverageRepos || "Register 3 repos with 2 tracked branches each.")}</p>
  `;
  return data;
}

async function refreshAll(showErrors = true) {
  try {
    await Promise.all([loadHealth(), loadRepositories(), loadQueue(), loadJobs(), loadWorkers(), loadSimulationStatus()]);
  } catch (error) {
    if (showErrors) {
      showFlash(error.message, true);
    }
  }
}

function setupTabs() {
  const buttons = document.querySelectorAll(".tab-button");
  const panels = document.querySelectorAll(".tab-panel");

  function activateTab(tabName, pushState = true) {
    buttons.forEach((item) => item.classList.toggle("active", item.getAttribute("data-tab") === tabName));
    panels.forEach((panel) => {
      panel.classList.toggle("active", panel.getAttribute("data-panel") === tabName);
    });

    if (pushState) {
      const url = new URL(window.location.href);
      url.searchParams.set("tab", tabName);
      window.history.replaceState({}, "", url);
    }
  }

  const initialTab = new URL(window.location.href).searchParams.get("tab");
  const validTabs = new Set(Array.from(buttons).map((button) => button.getAttribute("data-tab")));
  if (initialTab && validTabs.has(initialTab)) {
    activateTab(initialTab, false);
  }

  buttons.forEach((button) => {
    button.addEventListener("click", () => {
      const tabName = button.getAttribute("data-tab");
      activateTab(tabName);
    });
  });
}

function resetRepositoryForm() {
  elements.repositoryForm.reset();
  elements.repositoryForm.elements.namedItem("provider").value = "github";
  elements.repositoryForm.elements.namedItem("defaultBranch").value = "main";
  elements.repositoryForm.elements.namedItem("trackedBranches").value = "main, develop";
  elements.repositoryForm.elements.namedItem("pipelineFile").value = ".relay.yml";
  elements.repositoryForm.elements.namedItem("active").checked = true;
}

function setupRepositoryForm() {
  elements.repositoryForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const formData = new FormData(event.currentTarget);
    const payload = {
      fullName: String(formData.get("fullName") || "").trim(),
      provider: String(formData.get("provider") || "github").trim(),
      localPath: String(formData.get("localPath") || "").trim(),
      defaultBranch: String(formData.get("defaultBranch") || "main").trim(),
      trackedBranches: String(formData.get("trackedBranches") || "")
        .split(",")
        .map((branch) => branch.trim())
        .filter(Boolean),
      pipelineFile: String(formData.get("pipelineFile") || ".relay.yml").trim(),
      language: String(formData.get("language") || "").trim() || null,
      active: formData.get("active") === "on",
    };

    try {
      const result = await fetchJson("/repositories", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      showFlash(`${result.repository.fullName} saved to Relay. Verify it when ready.`);
      resetRepositoryForm();
      await Promise.all([loadRepositories(), loadQueue(), loadSimulationStatus()]);
    } catch (error) {
      showFlash(error.message, true);
    }
  });

  elements.resetRepositoryFormButton.addEventListener("click", resetRepositoryForm);
}

function setupButtons() {
  const refreshAllButton = document.getElementById("refreshAllButton");
  if (refreshAllButton) {
    refreshAllButton.addEventListener("click", () => refreshAll(true));
  }
  document.getElementById("refreshRepositoriesButton").addEventListener("click", () => loadRepositories().catch((error) => showFlash(error.message, true)));
  document.getElementById("refreshQueueButton").addEventListener("click", () => loadQueue().catch((error) => showFlash(error.message, true)));
  document.getElementById("refreshJobsButton").addEventListener("click", () => loadJobs().catch((error) => showFlash(error.message, true)));
  document.getElementById("refreshWorkersButton").addEventListener("click", () => loadWorkers().catch((error) => showFlash(error.message, true)));
  document.getElementById("refreshSimulationButton").addEventListener("click", () => loadSimulationStatus().catch((error) => showFlash(error.message, true)));

  document.getElementById("simulationStartForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const formData = new FormData(event.currentTarget);
    try {
      const result = await fetchJson("/simulation/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          minDelaySeconds: Number(formData.get("minDelaySeconds")),
          maxDelaySeconds: Number(formData.get("maxDelaySeconds")),
        }),
      });
      showFlash(result.message);
      await loadSimulationStatus();
    } catch (error) {
      showFlash(error.message, true);
    }
  });

  document.getElementById("stopSimulationButton").addEventListener("click", async () => {
    try {
      const result = await fetchJson("/simulation/stop", { method: "POST" });
      showFlash(result.message);
      await loadSimulationStatus();
    } catch (error) {
      showFlash(error.message, true);
    }
  });

  document.getElementById("simulationGenerateForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const formData = new FormData(event.currentTarget);
    try {
      const result = await fetchJson("/simulation/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ count: Number(formData.get("count")) }),
      });
      showFlash(`${result.message}: ${result.jobs.length} jobs created.`);
      await refreshAll(false);
    } catch (error) {
      showFlash(error.message, true);
    }
  });
}

function startAutoRefresh() {
  elements.autoRefreshLabel.textContent = `Live refresh every ${AUTO_REFRESH_MS / 1000}s`;
  state.autoRefreshId = window.setInterval(() => {
    refreshAll(false);
  }, AUTO_REFRESH_MS);
}

document.addEventListener("DOMContentLoaded", async () => {
  setupTabs();
  setupButtons();
  setupRepositoryForm();
  resetRepositoryForm();
  startAutoRefresh();
  await refreshAll(true);
});
