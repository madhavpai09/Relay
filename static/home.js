const AUTO_REFRESH_MS = 4000;

const elements = {
  heroHealthStatus: document.getElementById("heroHealthStatus"),
  heroRepositoryCount: document.getElementById("heroRepositoryCount"),
  heroVerifiedRepositoryCount: document.getElementById("heroVerifiedRepositoryCount"),
  heroJobCount: document.getElementById("heroJobCount"),
  heroWorkerCount: document.getElementById("heroWorkerCount"),
  heroQueuedJobCount: document.getElementById("heroQueuedJobCount"),
  autoRefreshLabel: document.getElementById("autoRefreshLabel"),
  overviewStatusList: document.getElementById("overviewStatusList"),
};

function escapeHtml(value) {
  return String(value ?? "—")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
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

async function loadHealth() {
  const health = await fetchJson("/health");
  elements.heroHealthStatus.textContent = `${health.status} / ${health.service}`;
  return health;
}

async function loadRepositories() {
  const data = await fetchJson("/repositories");
  const repositories = data.repositories || [];
  elements.heroRepositoryCount.textContent = String(repositories.length);
  elements.heroVerifiedRepositoryCount.textContent = String(
    repositories.filter((repo) => repo.verified).length,
  );
  return repositories;
}

async function loadJobs() {
  const data = await fetchJson("/jobs");
  elements.heroJobCount.textContent = String((data.jobs || []).length);
  return data.jobs || [];
}

async function loadWorkers() {
  const data = await fetchJson("/workers");
  elements.heroWorkerCount.textContent = String((data.workers || []).length);
  return data.workers || [];
}

async function loadQueue() {
  const data = await fetchJson("/queue");
  elements.heroQueuedJobCount.textContent = String(data.summary?.queuedCount ?? 0);
  return data;
}

function renderOverviewStatus({ repositories, jobs, workers, queue }) {
  const verifiedCount = repositories.filter((repo) => repo.verified).length;
  const activeJobs = jobs.filter((job) => ["received", "in_queue", "assigned", "processing"].includes(job.status)).length;
  const busyWorkers = (workers || []).filter((worker) => worker.currentJobId).length;

  elements.overviewStatusList.innerHTML = [
    `Verified repositories: ${verifiedCount} of ${repositories.length}`,
    `Active jobs in flight: ${activeJobs}`,
    `Queued jobs waiting: ${queue.summary?.queuedCount ?? 0}`,
    `Busy workers right now: ${busyWorkers} of ${workers.length}`,
  ]
    .map(
      (line) => `
        <article class="queue-item">
          <div class="meta-line">${escapeHtml(line)}</div>
        </article>
      `,
    )
    .join("");
}

async function refreshOverview() {
  const [health, repositories, jobs, workers, queue] = await Promise.all([
    loadHealth(),
    loadRepositories(),
    loadJobs(),
    loadWorkers(),
    loadQueue(),
  ]);
  renderOverviewStatus({ health, repositories, jobs, workers, queue });
}

document.addEventListener("DOMContentLoaded", async () => {
  elements.autoRefreshLabel.textContent = `Live refresh every ${AUTO_REFRESH_MS / 1000}s`;
  await refreshOverview();
  window.setInterval(() => {
    refreshOverview().catch(() => {
      elements.heroHealthStatus.textContent = "Unavailable";
    });
  }, AUTO_REFRESH_MS);
});
