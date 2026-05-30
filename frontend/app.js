const DATA_URL = "./data/gdpr_training_dataset.json";
const ENTITY_COLUMNS = [
  "PERSON",
  "EMAIL_ADDRESS",
  "PHONE_NUMBER",
  "LOCATION",
  "IBAN_CODE",
  "CREDIT_CARD",
  "PASSPORT",
  "NRP",
  "DATE_TIME",
  "IP_ADDRESS",
  "URL",
  "MEDICAL_LICENSE",
];

let allRows = [];
let findings = [];
let selectedFileId = null;

const stateById = new Map();

function statusFor(row) {
  if (!stateById.has(row.document_id)) stateById.set(row.document_id, "pending");
  return stateById.get(row.document_id);
}

function entitiesFor(row) {
  return ENTITY_COLUMNS.filter((entity) => row[`${entity}_yes_no`] === "yes");
}

function riskFor(row) {
  const entities = entitiesFor(row);
  if (row.retention_period_exceeded_3y === "yes" && entities.length >= 2) return "High";
  if (entities.includes("PASSPORT") || entities.includes("NRP") || entities.includes("MEDICAL_LICENSE")) return "High";
  if (entities.length >= 2) return "Medium";
  return "Low";
}

function countBy(rows, keyFn) {
  return rows.reduce((acc, row) => {
    const key = keyFn(row);
    acc[key] = (acc[key] || 0) + 1;
    return acc;
  }, {});
}

function renderKpis() {
  const scanned = allRows.length;
  const flagged = findings.length;
  const pending = findings.filter((row) => statusFor(row) === "pending").length;
  const retention = findings.filter((row) => row.retention_period_exceeded_3y === "yes").length;
  const highRisk = findings.filter((row) => riskFor(row) === "High").length;
  const kpis = [
    ["Scanned files", scanned],
    ["Flagged files", flagged],
    ["Finding rate", `${Math.round((flagged / scanned) * 100)}%`],
    ["Pending review", pending],
    ["High risk", highRisk],
    ["Retention exceeded", retention],
    ["Run mode", "Fixed seed"],
  ];

  document.querySelector("#kpi-grid").innerHTML = kpis
    .map(([label, value]) => `<article class="kpi"><span>${label}</span><strong>${value}</strong></article>`)
    .join("");
}

function renderBars(selector, entries, total, color = "#1f6feb") {
  document.querySelector(selector).innerHTML = entries
    .map(([label, value]) => {
      const percent = total ? Math.round((value / total) * 100) : 0;
      return `
        <div class="bar-row">
          <span>${label}</span>
          <div class="bar-track"><div class="bar-fill" style="width:${percent}%;background:${color}"></div></div>
          <strong>${value}</strong>
        </div>
      `;
    })
    .join("");
}

function renderDashboard() {
  renderKpis();

  const entityCounts = ENTITY_COLUMNS.map((entity) => [entity, findings.filter((row) => row[`${entity}_yes_no`] === "yes").length])
    .filter(([, value]) => value > 0)
    .sort((a, b) => b[1] - a[1]);

  const typeCounts = Object.entries(countBy(allRows, (row) => row.document_type)).sort((a, b) => a[0].localeCompare(b[0]));

  renderBars("#entity-bars", entityCounts, findings.length, "#d71920");
  renderBars("#type-bars", typeCounts, 100, "#1f6feb");

  const priorityRows = [...findings]
    .sort((a, b) => {
      const riskScore = { High: 3, Medium: 2, Low: 1 };
      return riskScore[riskFor(b)] - riskScore[riskFor(a)] || entitiesFor(b).length - entitiesFor(a).length;
    })
    .slice(0, 8);

  document.querySelector("#priority-list").innerHTML = priorityRows
    .map((row) => {
      const entities = entitiesFor(row);
      return `
        <article class="priority-item" data-id="${row.document_id}">
          <div class="item-title">
            <span>${row.file_name}</span>
            <span class="status pending">${riskFor(row)} risk</span>
          </div>
          <div class="meta">${row.responsible_owner} · ${row.document_type} · ${entities.join(", ")}</div>
        </article>
      `;
    })
    .join("");
}

function populateFilters() {
  const typeFilter = document.querySelector("#type-filter");
  const entityFilter = document.querySelector("#entity-filter");
  const ownerSelect = document.querySelector("#owner-select");

  [...new Set(allRows.map((row) => row.document_type))]
    .sort()
    .forEach((type) => typeFilter.insertAdjacentHTML("beforeend", `<option value="${type}">${type}</option>`));

  ENTITY_COLUMNS.forEach((entity) => entityFilter.insertAdjacentHTML("beforeend", `<option value="${entity}">${entity}</option>`));

  [...new Set(findings.map((row) => row.responsible_owner))]
    .sort()
    .forEach((owner) => ownerSelect.insertAdjacentHTML("beforeend", `<option value="${owner}">${owner}</option>`));
}

function filteredFindings() {
  const search = document.querySelector("#search-input").value.toLowerCase();
  const type = document.querySelector("#type-filter").value;
  const entity = document.querySelector("#entity-filter").value;
  const status = document.querySelector("#status-filter").value;

  return findings.filter((row) => {
    const entities = entitiesFor(row);
    const haystack = [row.file_name, row.document_type, row.responsible_owner, row.source_system, entities.join(" ")].join(" ").toLowerCase();
    return (
      (!search || haystack.includes(search)) &&
      (type === "all" || row.document_type === type) &&
      (entity === "all" || entities.includes(entity)) &&
      (status === "all" || statusFor(row) === status)
    );
  });
}

function renderFindingsTable() {
  const rows = filteredFindings();
  document.querySelector("#findings-table").innerHTML = rows
    .map((row) => {
      const entities = entitiesFor(row);
      const retention = row.retention_period_exceeded_3y === "yes";
      const status = statusFor(row);
      return `
        <tr>
          <td><strong>${row.file_name}</strong><div class="meta">${row.source_system}</div></td>
          <td>${row.document_type}</td>
          <td>${row.responsible_owner}</td>
          <td><div class="chips">${entities.map((entity) => `<span class="chip">${entity}</span>`).join("")}</div></td>
          <td>${row.last_modified_date}</td>
          <td class="${retention ? "retention" : ""}">${retention ? "Exceeded" : "OK"}</td>
          <td><span class="status ${status}">${status.replace("_", " ")}</span></td>
        </tr>
      `;
    })
    .join("");
}

function renderOwnerFiles() {
  const owner = document.querySelector("#owner-select").value;
  const rows = findings.filter((row) => row.responsible_owner === owner);
  if (!selectedFileId || !rows.some((row) => row.document_id === selectedFileId)) {
    selectedFileId = rows[0]?.document_id || null;
  }

  document.querySelector("#owner-files").innerHTML = rows
    .map((row) => `
      <article class="owner-file ${row.document_id === selectedFileId ? "active" : ""}" data-id="${row.document_id}">
        <div class="item-title">
          <span>${row.file_name}</span>
          <span class="status ${statusFor(row)}">${statusFor(row).replace("_", " ")}</span>
        </div>
        <div class="meta">${row.document_type} · ${entitiesFor(row).join(", ")}</div>
      </article>
    `)
    .join("");

  renderFileDetail();
}

function renderFileDetail() {
  const row = findings.find((item) => item.document_id === selectedFileId);
  if (!row) {
    document.querySelector("#file-detail").innerHTML = "<p>No assigned finding selected.</p>";
    return;
  }

  const entities = entitiesFor(row);
  document.querySelector("#file-detail").innerHTML = `
    <h3>${row.file_name}</h3>
    <div class="meta">${row.document_type} · ${row.source_system} · ${row.responsible_owner}</div>
    <div class="detail-grid">
      <div class="detail-card"><span>Created</span><strong>${row.file_created_date}</strong></div>
      <div class="detail-card"><span>Modified</span><strong>${row.last_modified_date}</strong></div>
      <div class="detail-card"><span>Risk</span><strong>${riskFor(row)}</strong></div>
      <div class="detail-card"><span>Retention</span><strong>${row.retention_period_exceeded_3y === "yes" ? "Exceeded" : "OK"}</strong></div>
      <div class="detail-card"><span>Status</span><strong>${statusFor(row).replace("_", " ")}</strong></div>
      <div class="detail-card"><span>Entities</span><strong>${entities.length}</strong></div>
    </div>
    <div class="chips">${entities.map((entity) => `<span class="chip">${entity}</span>`).join("")}</div>
    <div class="text-box">${row.full_text}</div>
    <div class="actions">
      <button data-action="confirmed">Confirm personal data</button>
      <button data-action="false_positive">Mark false positive</button>
      <button data-action="pending">Keep with reason</button>
      <button data-action="deletion_approved">Approve deletion</button>
    </div>
  `;
}

function setStatus(id, status) {
  stateById.set(id, status);
  renderDashboard();
  renderFindingsTable();
  renderOwnerFiles();
}

function runDeltaScanDemo() {
  const modifiedFiles = allRows.filter((row) => row.recommended_split === "test").slice(0, 12);
  const newFindings = modifiedFiles.filter((row) => row.contains_personal_data === "yes").length;
  document.querySelector("#scan-message").textContent =
    `Delta scan demo completed: ${modifiedFiles.length} modified files checked, ${newFindings} findings already reproducible from the stored labels.`;
}

function exportFindings() {
  const payload = findings.map((row) => ({
    document_id: row.document_id,
    file_name: row.file_name,
    document_type: row.document_type,
    owner: row.responsible_owner,
    status: statusFor(row),
    entities: entitiesFor(row),
    retention_period_exceeded_3y: row.retention_period_exceeded_3y,
  }));
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = "gdpr_findings_export.json";
  link.click();
  URL.revokeObjectURL(link.href);
  document.querySelector("#scan-message").textContent = "Findings export prepared as deterministic JSON.";
}

function bindEvents() {
  document.querySelectorAll(".nav-item").forEach((button) => {
    button.addEventListener("click", () => {
      document.querySelectorAll(".nav-item").forEach((item) => item.classList.remove("active"));
      button.classList.add("active");
      document.querySelectorAll(".view").forEach((view) => view.classList.remove("active"));
      document.querySelector(`#${button.dataset.view}-view`).classList.add("active");
      const titles = {
        dashboard: "Admin Overview",
        findings: "Admin Findings",
        review: "Employee Review",
      };
      document.querySelector("#page-title").textContent = titles[button.dataset.view];
    });
  });

  ["#search-input", "#type-filter", "#entity-filter", "#status-filter"].forEach((selector) => {
    document.querySelector(selector).addEventListener("input", renderFindingsTable);
  });

  document.querySelector("#owner-select").addEventListener("change", renderOwnerFiles);
  document.querySelector("#delta-scan-button").addEventListener("click", runDeltaScanDemo);
  document.querySelector("#export-button").addEventListener("click", exportFindings);

  document.addEventListener("click", (event) => {
    const card = event.target.closest(".owner-file, .priority-item");
    if (card) {
      selectedFileId = card.dataset.id;
      document.querySelector('[data-view="review"]').click();
      renderOwnerFiles();
    }

    const action = event.target.closest("[data-action]");
    if (action && selectedFileId) {
      setStatus(selectedFileId, action.dataset.action);
    }
  });
}

async function init() {
  const response = await fetch(DATA_URL);
  allRows = await response.json();
  findings = allRows.filter((row) => row.contains_personal_data === "yes");
  populateFilters();
  renderDashboard();
  renderFindingsTable();
  renderOwnerFiles();
  bindEvents();
}

init().catch((error) => {
  document.body.innerHTML = `<main class="main"><h2>Could not load dashboard data</h2><pre>${error.message}</pre></main>`;
});
