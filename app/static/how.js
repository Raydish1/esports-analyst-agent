// "How I got this": each step of the agent, its tool calls with their arguments or SQL, and the rows they returned,
// as the model saw them. Built with textContent only.

const ROWS_SHOWN = 25;

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = text;
  return node;
}

function value(v) {
  if (v === null || v === undefined) return "null";
  return typeof v === "object" ? JSON.stringify(v) : String(v);
}

function callText(call) {
  const args = Object.entries(call.arguments || {}).filter(([k]) => !(call.tool === "run_sql" && k === "query"));
  return `${call.tool}(${args.map(([k, v]) => `${k}=${typeof v === "string" ? JSON.stringify(v) : value(v)}`).join(", ")})`;
}

function sqlBlock(sql) {
  const pre = el("pre", "sql");
  pre.append(el("code", null, sql.trim()));
  return pre;
}

export function tableBlock(t) {
  const block = el("div", "result-table");
  const title = `${t.what} · ${t.row_count} row${t.row_count === 1 ? "" : "s"}`;
  block.append(el("div", "table-title", title));
  if (t.note) block.append(el("p", "table-note", t.note));
  if (!t.rows || !t.columns?.length) return block;
  const wrap = el("div", "table-wrap");
  const table = el("table");
  const head = table.createTHead().insertRow();
  for (const c of t.columns) head.append(el("th", null, c));
  const body = table.createTBody();
  const fill = (rows) => {
    body.replaceChildren();
    for (const row of rows) {
      const tr = body.insertRow();
      for (const v of row) {
        const td = tr.insertCell();
        td.textContent = value(v);
        if (v === null) td.className = "null";
      }
    }
  };
  fill(t.rows.slice(0, ROWS_SHOWN));
  wrap.append(table);
  block.append(wrap);
  if (t.rows.length > ROWS_SHOWN) {
    const more = el("button", "more", `Show all ${t.rows.length} rows`);
    more.type = "button";
    more.addEventListener("click", () => { fill(t.rows); more.remove(); });
    block.append(more);
  }
  return block;
}

function callBlock(call) {
  const block = el("div", "call");
  const head = el("div", "call-head");
  head.append(el("code", "call-name", callText(call)));
  if (call.seconds !== null && call.seconds !== undefined) head.append(el("span", "call-time", `${call.seconds} s`));
  if (call.refused) head.append(el("span", "badge bad", "refused"));
  block.append(head);
  const r = call.result;
  if (call.tool === "run_sql" && call.sql.length) block.append(sqlBlock(call.sql[0]));
  if (r.status) block.append(el("p", r.kind === "error" ? "status bad" : "status", r.status));
  for (const note of r.notes || []) block.append(el("p", "status note", note));
  if (r.sql) block.append(el("p", "status", `Event filter: ${r.sql}`));
  for (const t of r.tables || []) block.append(tableBlock(t));
  if (call.tool !== "run_sql" && call.sql.length) {
    const ran = el("details", "ran");
    ran.append(el("summary", null, `The SQL it ran (${call.sql.length} quer${call.sql.length === 1 ? "y" : "ies"})`));
    for (const sql of call.sql) ran.append(sqlBlock(sql));
    block.append(ran);
  }
  return block;
}

function stepBlock(step) {
  const block = el("section", "how-step");
  const title = `Step ${step.step}` + (step.seconds ? ` · ${step.seconds} s` : "");
  block.append(el("h4", null, title));
  if (step.thought) block.append(el("p", "thought", step.thought));
  for (const call of step.calls) block.append(callBlock(call));
  if (!step.calls.length && !step.checks.length) block.append(el("p", "status", "Wrote the answer."));
  for (const check of step.checks) {
    const box = el("div", "check");
    box.append(el("strong", null, `${check.check}: ${check.action}`));
    if (check.message) box.append(el("p", null, check.message));
    block.append(box);
  }
  for (const swap of step.name_swaps || []) {
    block.append(el("p", "status", `Name corrected in the answer: ${swap.from} → ${swap.to}`));
  }
  return block;
}

export function how(steps, examples) {
  const details = el("details", "how");
  details.append(el("summary", null, "How I got this"));
  const body = el("div", "how-body");
  if (examples?.length) {
    body.append(el("p", "examples-used", "Worked examples shown to the model: " +
      examples.map((e) => `${e.id} (${e.shape})`).join(", ")));
  }
  for (const step of steps) body.append(stepBlock(step));
  details.append(body);
  return details;
}
