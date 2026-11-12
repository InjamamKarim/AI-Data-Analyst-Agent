const state = { threadId: null, busy: false };

const banner = document.querySelector("#banner");
const hostLine = document.querySelector("#host-line");
const armSelect = document.querySelector("#arm");
const demoBox = document.querySelector("#demo");
const hitlBox = document.querySelector("#hitl");
const examples = document.querySelector("#examples");
const schema = document.querySelector("#schema");
const transcript = document.querySelector("#transcript");
const form = document.querySelector("#composer");
const questionBox = document.querySelector("#question");
const sendButton = document.querySelector("#send");
const uploadForm = document.querySelector("#upload-form");
const uploadNote = document.querySelector("#upload-note");

form.addEventListener("submit", (event) => {
  event.preventDefault();
  ask(questionBox.value);
});

uploadForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const file = document.querySelector("#csv").files[0];
  if (!file) {
    uploadNote.textContent = "Choose a CSV first.";
    return;
  }
  const body = new FormData();
  body.append("file", file);
  uploadNote.textContent = "Loading…";
  const response = await fetch("/api/upload", { method: "POST", body });
  const payload = await response.json();
  if (!response.ok) {
    uploadNote.textContent = payload.detail || "Upload failed.";
    return;
  }
  uploadNote.textContent = payload.sql_table
    ? `Loaded ${payload.rows} rows into ${payload.sql_table}.`
    : `Saved ${payload.rows} rows for the Python sandbox.`;
  loadSchema();
});

boot();

async function boot() {
  const [health, arms, sample, tables] = await Promise.all([
    getJSON("/api/health"),
    getJSON("/api/arms"),
    getJSON("/api/examples"),
    getJSON("/api/schema"),
  ]);
  renderHost(health);
  arms.forEach((arm) => {
    const option = document.createElement("option");
    option.value = arm.id;
    option.textContent = `${arm.id}. ${arm.title}`;
    if (arm.id === "G") option.selected = true;
    armSelect.append(option);
  });
  demoBox.checked = !health.nvidia_api_key_configured;
  sample.forEach((item) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "secondary";
    button.textContent = item.question;
    button.addEventListener("click", () => ask(item.question));
    examples.append(button);
  });
  const safety = document.createElement("button");
  safety.type = "button";
  safety.className = "danger";
  safety.textContent = "Safety check: Delete all users from the database";
  safety.addEventListener("click", () => ask("Delete all users from the database"));
  examples.append(safety);
  renderSchema(tables);
}

function renderHost(health) {
  const gpu = health.host && health.host.gpu;
  const memory = health.host && health.host.memory;
  const memoryText = memory && memory.total_gb ? `${memory.total_gb} GB RAM` : "memory unknown";
  hostLine.textContent = gpu && gpu.available
    ? `GPU ${gpu.name || "present"} at ${gpu.utilization_percent ?? "?"}% · ${memoryText}`
    : `No local NVIDIA GPU · ${memoryText} · model stays on the free NVIDIA API`;
  if (!health.nvidia_api_key_configured) {
    banner.hidden = false;
    banner.textContent = "NVIDIA_API_KEY is empty. Demo mode answers the 50 sample questions on the local database. Add a free key from build.nvidia.com/settings to .env when you want open-ended questions. No model is loaded on this machine.";
  }
}

function renderSchema(tables) {
  schema.replaceChildren();
  tables.forEach((table) => {
    const details = document.createElement("details");
    const summary = document.createElement("summary");
    summary.textContent = `${table.name}${table.view ? " (view)" : ""}`;
    const copy = document.createElement("p");
    copy.textContent = `${table.columns.join(", ")}. ${table.description}`;
    details.append(summary, copy);
    schema.append(details);
  });
}

async function ask(message) {
  const question = (message || "").trim();
  if (!question || state.busy) return;
  state.busy = true;
  sendButton.disabled = true;
  questionBox.value = question;
  const response = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      message: question,
      thread_id: state.threadId,
      arm: armSelect.value,
      demo: demoBox.checked,
      hitl: hitlBox.checked,
    }),
  });
  const payload = await response.json();
  state.busy = false;
  sendButton.disabled = false;
  if (!response.ok) {
    renderTurn(question, { output: payload.detail || "Request failed." });
    return;
  }
  state.threadId = payload.thread_id;
  renderTurn(question, payload);
}

async function resume(approved) {
  if (!state.threadId || state.busy) return;
  state.busy = true;
  const response = await fetch("/api/chat/resume", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ thread_id: state.threadId, approved }),
  });
  const payload = await response.json();
  state.busy = false;
  renderTurn(approved ? "Approved" : "Rejected", payload);
}

function renderTurn(question, payload) {
  const card = document.createElement("article");
  card.className = "turn";
  if (payload.blocked || payload.rejected) card.classList.add("warning");
  if (payload.demo) card.classList.add("demo");

  const title = document.createElement("p");
  title.className = "question";
  title.textContent = question;
  card.append(title);

  const answer = document.createElement("div");
  answer.className = "answer";
  answer.textContent = payload.output || "";
  card.append(answer);

  if (payload.demo) {
    card.append(note("Demo mode replayed curated SQL. This is not a live model answer."));
  }
  if (payload.sql) {
    card.append(block("SQL", payload.sql));
  }
  if (payload.blocked_sql) {
    card.append(block("Blocked SQL", payload.blocked_sql));
  }
  if (payload.rows && payload.rows.length) {
    card.append(table(payload.columns, payload.rows));
  }
  if (payload.python) {
    card.append(block("Python", payload.python));
  }
  if (payload.python_output) {
    card.append(block("Python output", payload.python_output));
  }
  if (payload.chart_url) {
    const image = document.createElement("img");
    image.className = "chart";
    image.alt = "Chart from the sandbox";
    image.src = payload.chart_url;
    card.append(image);
  }
  if (payload.interrupted && payload.interrupt) {
    const actions = document.createElement("div");
    actions.className = "actions";
    const approve = document.createElement("button");
    approve.type = "button";
    approve.textContent = "Approve";
    approve.addEventListener("click", () => resume(true));
    const reject = document.createElement("button");
    reject.type = "button";
    reject.className = "danger";
    reject.textContent = "Reject";
    reject.addEventListener("click", () => resume(false));
    actions.append(approve, reject);
    card.append(block("Plan waiting for review", payload.interrupt.sql || payload.interrupt.message || ""));
    card.append(actions);
  }
  const meta = document.createElement("p");
  meta.className = "meta";
  meta.textContent = `Arm ${payload.arm || "—"} · ${payload.latency_s ?? "—"}s · ~${payload.tokens || 0} tokens`;
  card.append(meta);
  transcript.append(card);
  card.scrollIntoView({ block: "nearest" });
}

function block(title, text) {
  const wrap = document.createElement("div");
  const heading = document.createElement("p");
  heading.className = "meta";
  heading.textContent = title;
  const pre = document.createElement("pre");
  pre.textContent = text;
  wrap.append(heading, pre);
  return wrap;
}

function note(text) {
  const line = document.createElement("p");
  line.className = "note";
  line.textContent = text;
  return line;
}

function table(columns, rows) {
  const element = document.createElement("table");
  const head = document.createElement("tr");
  columns.forEach((column) => {
    const cell = document.createElement("th");
    cell.textContent = column;
    head.append(cell);
  });
  element.append(head);
  rows.slice(0, 20).forEach((row) => {
    const line = document.createElement("tr");
    columns.forEach((column) => {
      const cell = document.createElement("td");
      cell.textContent = row[column] == null ? "" : String(row[column]);
      line.append(cell);
    });
    element.append(line);
  });
  return element;
}

async function loadSchema() {
  renderSchema(await getJSON("/api/schema"));
}

async function getJSON(url) {
  const response = await fetch(url);
  if (!response.ok) throw new Error(url);
  return response.json();
}
