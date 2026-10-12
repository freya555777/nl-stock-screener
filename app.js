/* 选股意图解释器 · 前端逻辑 */
"use strict";

const $ = (id) => document.getElementById(id);
const state = {
  meta: null,
  conditions: [],       // 当前结构化条件
  lastResult: null,     // 最近一次筛选结果
  selected: new Set(),  // 比较用勾选
  quoteApplied: false,
};

/* ---------------- API 封装 ---------------- */
async function api(path, body, method) {
  const resp = await fetch(path, {
    method: method || (body === undefined ? "GET" : "POST"),
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  let payload = null;
  try { payload = await resp.json(); } catch (e) { /* 非JSON */ }
  if (!resp.ok || !payload || payload.code !== 0) {
    throw new Error((payload && payload.message) || `请求失败(${resp.status})`);
  }
  return payload.data;
}

/* ---------------- 初始化 ---------------- */
async function init() {
  try {
    const meta = await api("/api/meta");
    state.meta = meta;
    renderExamples(meta.examples || []);
    renderIndustrySelect(meta.industries || []);
    $("dataModeBadge").textContent = meta.data_status.mode === "demo" ? "演示数据" : "扶摇数据";
    $("llmBadge").textContent = meta.llm_configured ? "LLM 解析" : "规则解析";
    if (meta.quote_state && meta.quote_state.applied_count > 0) markQuotesApplied(meta.quote_state);
    loadSaves();
  } catch (e) {
    $("dataBanner").innerHTML = "<strong>初始化失败：</strong>" + e.message;
  }
}

function renderExamples(examples) {
  const box = $("exampleChips");
  box.innerHTML = "";
  examples.forEach((ex) => {
    const chip = document.createElement("span");
    chip.className = "chip";
    chip.textContent = ex;
    chip.onclick = () => { $("intentInput").value = ex; parseIntent(); };
    box.appendChild(chip);
  });
}

function renderIndustrySelect(industries) {
  const sel = $("industryExcludeSelect");
  sel.innerHTML = "";
  industries.forEach((ind) => {
    const opt = document.createElement("option");
    opt.value = ind;
    opt.textContent = ind;
    sel.appendChild(opt);
  });
}

/* ---------------- 解析 ---------------- */
async function parseIntent() {
  const text = $("intentInput").value.trim();
  if (!text) { $("parseStatus").textContent = "请输入选股意图。"; return; }
  $("parseStatus").textContent = "解析中…";
  try {
    const r = await api("/api/parse", { text });
    state.conditions = r.conditions;
    state.lastResult = null;
    state.selected.clear();
    renderParsed(r);
    $("parsedCard").style.display = "";
    $("resultCard").style.display = "none";
    $("whatifCard").style.display = "none";
    $("backtestCard").style.display = "none";
    $("parseStatus").textContent = "";
  } catch (e) {
    $("parseStatus").textContent = "";
    showMsg("parseStatus", e.message, "error");
  }
}

function showMsg(id, text, kind) {
  const el = $(id);
  if (!el) return;
  el.innerHTML = '<span class="msgbox msg-' + (kind || "info") + '">' + esc(text) + "</span>";
}

function renderParsed(r) {
  $("summaryLine").textContent = (r.source === "llm" ? "[LLM] " : "[规则] ") + r.summary;
  renderConflicts(r.conflicts || []);
  renderClarify(r.clarifications || []);
  renderMissing(r.missing_data || []);
  renderConditions();
}

function renderConflicts(conflicts) {
  const box = $("conflictBox");
  box.innerHTML = "";
  conflicts.forEach((c) => {
    const div = document.createElement("div");
    div.className = "msgbox " + (c.level === "error" ? "msg-error" : "msg-warn");
    div.textContent = (c.level === "error" ? "⚠ 条件冲突：" : "⚠ 请注意：") + c.message;
    box.appendChild(div);
  });
}
function renderClarify(items) {
  const box = $("clarifyBox");
  box.innerHTML = "";
  items.forEach((t) => {
    const div = document.createElement("div");
    div.className = "msgbox msg-info";
    div.textContent = "口径说明：" + t;
    box.appendChild(div);
  });
}
function renderMissing(items) {
  const box = $("missingBox");
  box.innerHTML = "";
  items.forEach((t) => {
    const div = document.createElement("div");
    div.className = "msgbox msg-gray";
    div.textContent = "未覆盖维度：" + t;
    box.appendChild(div);
  });
}

/* ---------------- 条件编辑器 ---------------- */
const META = () => state.meta;

function renderConditions() {
  const box = $("conditionsEditor");
  box.innerHTML = "";
  state.conditions.forEach((cond, idx) => {
    const card = document.createElement("div");
    card.className = "cond-card";
    if (cond.type === "exclude_st") {
      card.innerHTML =
        '<span class="tag">特殊条件</span><strong>剔除 ST / *ST</strong>' +
        '<span class="tag">（演示口径标注）</span>' + delBtn(idx);
    } else if (cond.type === "industry_exclude") {
      card.innerHTML =
        '<span class="tag">特殊条件</span><strong>排除行业：</strong>' +
        cond.value.map((v) => '<span class="tag" style="background:#e8f0fe;border-radius:6px;padding:2px 8px;">' + esc(v) + "</span>").join(" ") +
        delBtn(idx);
    } else {
      const m = META().metrics[cond.metric];
      const ops = META().ops;
      card.innerHTML =
        metricSelect(idx, cond.metric) + opSelect(idx, cond.op) + valueInputs(idx, cond) +
        '<span class="tag">' + esc(m.unit) + "</span>" + delBtn(idx);
    }
    box.appendChild(card);
  });
  // 敏感性下拉
  const ws = $("whatifSelect");
  ws.innerHTML = "";
  state.conditions.forEach((c, i) => {
    if (!c.metric) return;
    const opt = document.createElement("option");
    opt.value = i;
    opt.textContent = c.metric + "（" + META().metrics[c.metric].label + "）";
    ws.appendChild(opt);
  });
}

function delBtn(idx) {
  return '<button class="btn-del" title="删除该条件" onclick="removeCondition(' + idx + ')">✕</button>';
}

function metricSelect(idx, metric) {
  const cats = {};
  Object.values(META().metrics).forEach((m) => {
    (cats[m.category] = cats[m.category] || []).push(m);
  });
  let html = '<select data-idx="' + idx + '" data-field="metric">';
  Object.keys(cats).forEach((cat) => {
    html += '<optgroup label="' + esc(cat) + '">';
    cats[cat].forEach((m) => {
      html += '<option value="' + m.id + '"' + (m.id === metric ? " selected" : "") + ">" + esc(m.label) + "</option>";
    });
    html += "</optgroup>";
  });
  html += "</select>";
  return html;
}

function opSelect(idx, op) {
  let html = '<select data-idx="' + idx + '" data-field="op">';
  Object.keys(META().ops).forEach((k) => {
    html += '<option value="' + k + '"' + (k === op ? " selected" : "") + ">" + esc(META().ops[k].label) + "</option>";
  });
  html += "</select>";
  return html;
}

function valueInputs(idx, cond) {
  const nv = META().ops[cond.op].n_values;
  if (nv === 2) {
    const v = cond.value || [0, 100];
    return '<input class="input-inline" style="width:80px" type="number" data-idx="' + idx + '" data-field="v0" value="' + v[0] + '">' +
           "<span>—</span>" +
           '<input class="input-inline" style="width:80px" type="number" data-idx="' + idx + '" data-field="v1" value="' + v[1] + '">';
  }
  return '<input class="input-inline" style="width:90px" type="number" step="any" data-idx="' + idx + '" data-field="v0" value="' + (cond.value ?? "") + '">';
}

/* 事件委托：条件编辑器变化 → 同步 state.conditions */
$("conditionsEditor").addEventListener("change", (ev) => {
  const t = ev.target;
  const idx = +t.dataset.idx;
  if (isNaN(idx) || !state.conditions[idx]) return;
  const c = state.conditions[idx];
  if (t.dataset.field === "metric") { c.metric = t.value; renderConditions(); return; }
  if (t.dataset.field === "op") {
    c.op = t.value;
    if (META().ops[c.op].n_values === 2) c.value = [0, 100];
    else if (Array.isArray(c.value)) c.value = c.value[0];
    renderConditions();
    return;
  }
  if (t.dataset.field === "v0" || t.dataset.field === "v1") {
    if (META().ops[c.op].n_values === 2) {
      const v = c.value && Array.isArray(c.value) ? c.value.slice() : [0, 100];
      v[t.dataset.field === "v0" ? 0 : 1] = parseFloat(t.value);
      c.value = v;
    } else {
      c.value = parseFloat(t.value);
    }
  }
});

$("btnAddCondition").onclick = () => {
  state.conditions.push({ metric: "pe_ttm", op: "le", value: 40 });
  renderConditions();
};
$("btnAddExcludeST").onclick = () => {
  if (!state.conditions.some((c) => c.type === "exclude_st")) {
    state.conditions.push({ type: "exclude_st" });
    renderConditions();
  }
};
$("btnAddIndustryExclude").onclick = () => {
  const ind = $("industryExcludeSelect").value;
  const ex = state.conditions.find((c) => c.type === "industry_exclude");
  if (ex) { if (!ex.value.includes(ind)) ex.value.push(ind); }
  else state.conditions.push({ type: "industry_exclude", value: [ind] });
  renderConditions();
};

function removeCondition(idx) {
  state.conditions.splice(idx, 1);
  if (!state.conditions.length) state.conditions.push({ metric: "pe_ttm", op: "le", value: 40 });
  renderConditions();
}

/* ---------------- 筛选 ---------------- */
async function runScreen() {
  if (!state.conditions.length) { $("screenStatus").textContent = "请先添加条件。"; return; }
  $("screenStatus").textContent = "筛选中…";
  try {
    const r = await api("/api/screen", { conditions: state.conditions, limit: 30 });
    state.lastResult = r;
    state.selected.clear();
    renderResult(r);
    $("resultCard").style.display = "";
    $("whatifCard").style.display = "";
    $("screenStatus").textContent = "";
  } catch (e) {
    $("screenStatus").textContent = "";
    showMsg("screenStatus", e.message, "error");
  }
}

function renderResult(r) {
  const dm = state.quoteApplied ? "实时行情 + 演示财务" : "演示数据";
  $("resultSummary").innerHTML =
    "命中 <b>" + r.included.length + "</b> / " + r.universe_size + " 只（条件：" +
    esc(r.conditions.join("；")) + "）｜数据模式：" + dm +
    "｜生成时间 " + esc(r.generated_at) + "｜被排除 " + r.excluded_total + " 只（含数据缺失 " + r.excluded_missing + "）";
  const tbody = $("resultTable").querySelector("tbody");
  tbody.innerHTML = "";
  r.included.forEach((s) => tbody.appendChild(resultRow(s, true)));
  if ($("chkShowExcluded").checked) {
    r.excluded_near_miss.forEach((s) => tbody.appendChild(resultRow(s, false)));
  }
  $("btnCompare").disabled = true;
  $("btnCompare").textContent = "比较所选（0）";
  renderNearMiss(r);
}

function resultRow(s, included) {
  const tr = document.createElement("tr");
  tr.dataset.code = s.code;
  const tag = included
    ? '<span class="tag-result tag-in">入选</span><span class="explain">满足度 ' + s.score + "%</span>"
    : (s.has_missing
        ? '<span class="tag-result tag-missing">数据缺失</span>'
        : '<span class="tag-result tag-out">排除</span>') +
      '<span class="explain">' + esc((s.fail_reasons || []).join("；") || (s.min_gap_text || "")) + "</span>";
  const m = s.metrics || {};
  tr.innerHTML =
    '<td onclick="event.stopPropagation()"><input type="checkbox" class="row-check" data-code="' + s.code + '"' + (state.selected.has(s.code) ? " checked" : "") + "></td>" +
    "<td>" + esc(s.code) + "</td><td><b>" + esc(s.name) + "</b></td>" +
    "<td>" + esc(s.sector) + "/" + esc(s.industry) + "</td>" +
    "<td>" + tag + "</td>" +
    "<td>" + (included ? s.score : "—") + "</td>" +
    "<td>" + esc(m.pe_ttm ?? "—") + "</td><td>" + esc(m.pb ?? "—") + "</td><td>" + esc(m.roe ?? "—") + "</td>" +
    "<td>" + esc(m.profit_yoy ?? "—") + "</td><td>" + esc(m.mkt_cap ?? "—") + "</td><td>" + esc(m.vol_20d ?? "—") + "</td>" +
    "<td>" + esc(m.dividend_yield ?? "—") + "</td><td>" + esc(m.mom_60d ?? "—") + "</td>";
  tr.onclick = () => openDetail(s.code);
  return tr;
}

function renderNearMiss(r) {
  const box = $("nearMissBlock");
  box.innerHTML = "";
  if (!r.excluded_near_miss.length) return;
  box.innerHTML = '<div class="section-title">接近入选（差距最小，但未满足全部条件）</div>' +
    '<p class="muted small">点击行可查看逐条件差距。完整被排除列表可在详情中查看决定性原因。</p>';
  const table = document.createElement("table");
  table.innerHTML = "<thead><tr><th>代码</th><th>名称</th><th>行业</th><th>决定性原因</th><th>PE</th><th>ROE</th><th>净利同比</th><th>波动率</th></tr></thead><tbody></tbody>";
  const tbody = table.querySelector("tbody");
  r.excluded_near_miss.forEach((s) => {
    const tr = document.createElement("tr");
    tr.dataset.code = s.code;
    const m = s.metrics || {};
    tr.innerHTML =
      "<td>" + esc(s.code) + "</td><td><b>" + esc(s.name) + "</b></td><td>" + esc(s.industry) + "</td>" +
      "<td><span class='explain'>" + esc((s.fail_reasons || []).join("；")) + "</span></td>" +
      "<td>" + esc(m.pe_ttm ?? "—") + "</td><td>" + esc(m.roe ?? "—") + "</td><td>" + esc(m.profit_yoy ?? "—") + "</td><td>" + esc(m.vol_20d ?? "—") + "</td>";
    tr.onclick = () => openDetail(s.code);
    tbody.appendChild(tr);
  });
  box.appendChild(table);
}

/* 勾选/比较 */
$("resultTable").addEventListener("change", (ev) => {
  if (!ev.target.classList.contains("row-check")) return;
  const code = ev.target.dataset.code;
  if (ev.target.checked) state.selected.add(code); else state.selected.delete(code);
  $("btnCompare").disabled = state.selected.size < 2;
  $("btnCompare").textContent = "比较所选（" + state.selected.size + "）";
});
$("chkShowExcluded").onchange = () => { if (state.lastResult) renderResult(state.lastResult); };

async function openDetail(code) {
  const r = state.lastResult;
  let stock = null;
  if (r) {
    stock = r.included.find((s) => s.code === code) || r.excluded_near_miss.find((s) => s.code === code);
  }
  let rowsHtml = "";
  if (stock) {
    rowsHtml = stock.checks.map((c) => {
      const dot = c.missing ? "dot-miss" : (c.passed ? "dot-in" : "dot-out");
      const label = c.missing ? "数据缺失" : (c.passed ? "通过" : "未通过");
      const reason = c.reason ? '<span class="explain">' + esc(c.reason) + "</span>" : "";
      return '<div class="check-row"><span class="dot ' + dot + '"></span><b>' + esc(c.condition) + "</b>" +
             '<span class="actual">' + esc(c.actual_text || "—") + "</span>" +
             '<span class="tag ' + (c.missing ? "badge-amber" : (c.passed ? "badge-green" : "badge-gray")) + '">' + label + "</span>" + reason + "</div>";
    }).join("");
  }
  const m = stock ? stock.metrics : {};
  openModal(
    "<button class='modal-close' onclick='closeModal()'>✕</button>" +
    "<h3>" + esc(stock ? stock.name : code) + "（" + esc(code) + "）— 入选解释</h3>" +
    (stock ? "<p class='muted small'>板块：" + esc(stock.sector) + "/" + esc(stock.industry) +
      "｜满足度：" + (stock.score ?? "—") + "%</p>" : "") +
    "<div class='section-title'>逐条件核验</div>" +
    (rowsHtml || "<p class='muted'>暂无逐条件数据</p>") +
    "<div class='section-title'>关键指标</div>" +
    "<p class='small'>" + Object.keys(m).map((k) => esc(META().metrics[k].label) + " " + esc(m[k] ?? "—")).join("　") + "</p>" +
    "<p class='muted small'>口径：行情字段来源与财务演示口径逐字段标注；数据缺失不判定为「未通过」。</p>"
  );
}

function openModal(html) {
  $("modal").innerHTML = html;
  $("modal").style.display = "block";
  $("modalMask").style.display = "block";
}
function closeModal() {
  $("modal").style.display = "none";
  $("modalMask").style.display = "none";
}

/* ---------------- 比较 ---------------- */
$("btnCompare").onclick = async () => {
  if (state.selected.size < 2) return;
  try {
    const r = await api("/api/compare", { codes: [...state.selected], conditions: state.conditions });
    let html = "<button class='modal-close' onclick='closeModal()'>✕</button><h3>横向比较（" + r.rows.length + " 只）</h3>";
    html += "<table><thead><tr><th>代码</th><th>名称</th><th>行业</th>";
    r.columns.forEach((c) => { html += "<th>" + esc(META().metrics[c].label) + "</th>"; });
    html += "</tr></thead><tbody>";
    r.rows.forEach((row) => {
      html += "<tr><td>" + esc(row.code) + "</td><td><b>" + esc(row.name) + "</b></td><td>" + esc(row.industry) + "</td>";
      r.columns.forEach((c) => { html += "<td>" + esc(row.metrics[c] ?? "—") + "</td>"; });
      html += "</tr>";
    });
    html += "</tbody></table>";
    if (state.conditions.length) {
      html += "<div class='section-title'>当前条件下各标的通过情况</div>";
      html += r.rows.map((row) =>
        "<div class='check-row'><b>" + esc(row.name) + "</b>" +
        row.checks.map((c) =>
          '<span class="tag ' + (c.missing ? "badge-amber" : (c.passed ? "badge-green" : "badge-gray")) + '">' +
          esc(c.condition) + " " + esc(c.actual_text || "—") + "</span>").join(" ") + "</div>").join("");
    }
    openModal(html);
  } catch (e) { alert(e.message); }
};

/* ---------------- 敏感性 ---------------- */
$("btnWhatif").onclick = async () => {
  const idx = +$("whatifSelect").value;
  const c = state.conditions[idx];
  if (!c || !c.metric) { alert("请先在条件面板添加指标条件。"); return; }
  let raw = $("whatifValue").value.trim();
  let value;
  if (META().ops[c.op].n_values === 2) {
    const parts = raw.split(/[,，\s]+/).map(parseFloat);
    if (parts.length !== 2 || isNaN(parts[0]) || isNaN(parts[1])) { alert("区间条件请填写 lo,hi，例如 10,40"); return; }
    value = parts;
  } else {
    value = parseFloat(raw);
    if (isNaN(value)) { alert("请填写数值阈值。"); return; }
  }
  try {
    const r = await api("/api/whatif", { conditions: state.conditions, metric: c.metric, value });
    let html = "<div class='section-title'>修改「" + esc(r.metric_label) + "」为 " + esc(r.new_condition_text) + "</div>";
    html += "<p class='summary'>入选数量：" + r.before_count + " → <b>" + r.after_count + "</b>（新增 " + r.added_count + "，掉出 " + r.removed_count + "）</p>";
    if (r.added.length) {
      html += "<div class='section-title'>新增入选</div>" + r.added.map((s) =>
        "<span class='tag-result tag-in'>+</span> " + esc(s.name) + "（" + esc(s.code) + "）满足度 " + s.score + "%").join("<br>");
    }
    if (r.removed.length) {
      html += "<div class='section-title'>掉出候选</div>" + r.removed.map((s) =>
        "<span class='tag-result tag-out'>-</span> " + esc(s.name) + "（" + esc(s.code) + "）").join("<br>");
    }
    html += "<p class='muted small'>" + esc(r.note) + "</p>";
    $("whatifResult").innerHTML = html;
  } catch (e) { alert(e.message); }
};

/* ---------------- 回测 ---------------- */
$("btnBacktest").onclick = async () => {
  let codes = [...state.selected];
  if (!codes.length && state.lastResult) codes = state.lastResult.included.map((s) => s.code);
  if (!codes.length) { alert("当前没有可回测的标的：请先筛选，或勾选若干股票。"); return; }
  try {
    const r = await api("/api/backtest", { codes, days: 20 });
    $("backtestCard").style.display = "";
    $("backtestMeta").innerHTML =
      "组合（等权 " + r.stock_count + " 只，" + r.days + " 日）收益：<b>" + r.portfolio_ret_pct + "%</b>　" +
      "沪深300（模拟基准）：" + r.benchmark_ret_pct + "%　超额：" + r.excess_pct + "%<br>" +
      '<span class="muted small">' + esc(r.note) + "</span>";
    drawChart(r.dates, r.portfolio_series, r.benchmark_series);
    $("backtestTableWrap").innerHTML =
      "<table><thead><tr><th>代码</th><th>名称</th><th>行业</th><th>区间收益</th><th>演示波动率</th></tr></thead><tbody>" +
      r.rows.map((x) => "<tr><td>" + esc(x.code) + "</td><td><b>" + esc(x.name) + "</b></td><td>" + esc(x.industry) + "</td><td>" + x.ret_pct + "%</td><td>" + (x.vol_pct ?? "—") + "%</td></tr>").join("") +
      "</tbody></table>";
  } catch (e) { alert(e.message); }
};

function drawChart(dates, pf, bench) {
  const canvas = $("btChart");
  const dpr = window.devicePixelRatio || 1;
  const W = canvas.clientWidth || 900, H = 300;
  canvas.width = W * dpr; canvas.height = H * dpr;
  canvas.style.width = W + "px"; canvas.style.height = H + "px";
  const ctx = canvas.getContext("2d");
  ctx.scale(dpr, dpr);
  ctx.clearRect(0, 0, W, H);
  const pad = { l: 52, r: 14, t: 16, b: 26 };
  const all = pf.concat(bench);
  let min = Math.min(...all), max = Math.max(...all);
  const span = max - min || 1; min -= span * 0.08; max += span * 0.08;
  const x = (i) => pad.l + i * (W - pad.l - pad.r) / (dates.length - 1);
  const y = (v) => pad.t + (1 - (v - min) / (max - min)) * (H - pad.t - pad.b);
  // 网格
  ctx.strokeStyle = "#e8eaed"; ctx.fillStyle = "#6b7280"; ctx.font = "11px sans-serif";
  for (let g = 0; g <= 4; g++) {
    const v = min + (max - min) * g / 4, gy = y(v);
    ctx.beginPath(); ctx.moveTo(pad.l, gy); ctx.lineTo(W - pad.r, gy); ctx.stroke();
    ctx.fillText(v.toFixed(1), 6, gy + 4);
  }
  ctx.fillText(dates[0], pad.l, H - 8);
  ctx.fillText(dates[dates.length - 1], W - pad.r - 34, H - 8);
  const line = (data, color) => {
    ctx.strokeStyle = color; ctx.lineWidth = 2; ctx.beginPath();
    data.forEach((v, i) => (i ? ctx.lineTo(x(i), y(v)) : ctx.moveTo(x(i), y(v))));
    ctx.stroke();
  };
  line(pf, "#1a73e8");
  line(bench, "#e37400");
  // 图例
  ctx.fillStyle = "#1a73e8"; ctx.fillRect(pad.l, 8, 10, 10);
  ctx.fillStyle = "#333"; ctx.fillText("组合（等权）", pad.l + 14, 17);
  ctx.fillStyle = "#e37400"; ctx.fillRect(pad.l + 110, 8, 10, 10);
  ctx.fillStyle = "#333"; ctx.fillText("沪深300（模拟基准）", pad.l + 124, 17);
}

/* ---------------- 保存策略 ---------------- */
$("btnSave").onclick = async () => {
  let codes = [...state.selected];
  if (!codes.length && state.lastResult) codes = state.lastResult.included.map((s) => s.code);
  const name = $("saveName").value.trim() || "未命名策略 " + new Date().toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" });
  try {
    await api("/api/saves", { name, conditions: state.conditions, codes });
    $("saveName").value = "";
    loadSaves();
  } catch (e) { alert(e.message); }
};

async function loadSaves() {
  try {
    const r = await api("/api/saves");
    const box = $("savedList");
    if (!r.saves.length) { box.innerHTML = '<p class="muted">暂无保存的策略。</p>'; return; }
    box.innerHTML = "";
    r.saves.forEach((s) => {
      const div = document.createElement("div");
      div.className = "save-item";
      div.innerHTML =
        '<span class="name">' + esc(s.name) + "</span>" +
        '<span class="time">' + esc(s.created_at) + "</span>" +
        '<span class="conds">' + esc(s.conditions.length + " 个条件 · " + s.codes.length + " 只标的") + "</span>" +
        "<button class='btn btn-ghost' onclick='loadSave(\"" + s.id + "\")'>加载</button>" +
        "<button class='btn btn-ghost' onclick='deleteSave(\"" + s.id + "\")'>删除</button>";
      box.appendChild(div);
    });
  } catch (e) { /* 忽略 */ }
}

async function loadSave(id) {
  try {
    const r = await api("/api/saves");
    const s = r.saves.find((x) => x.id === id);
    if (!s) return;
    state.conditions = JSON.parse(JSON.stringify(s.conditions));
    renderParsed({ source: "saved", summary: "已加载策略「" + s.name + "」，共 " + s.conditions.length + " 个条件", conflicts: [], clarifications: [], missing_data: [] });
    $("parsedCard").style.display = "";
    runScreen();
  } catch (e) { alert(e.message); }
}

async function deleteSave(id) {
  try { await api("/api/saves/" + id, undefined, "DELETE"); loadSaves(); }
  catch (e) { alert(e.message); }
}

/* ---------------- 实时行情 ---------------- */
$("btnRefreshQuotes").onclick = async () => {
  $("btnRefreshQuotes").disabled = true;
  $("btnRefreshQuotes").textContent = "刷新中…";
  try {
    const r = await api("/api/quotes/refresh", {});
    markQuotesApplied(r.state);
    $("btnRefreshQuotes").textContent = "刷新实时行情";
    if (state.lastResult && state.conditions.length) await runScreen();
    else if (state.conditions.length) await runScreen();
  } catch (e) {
    $("btnRefreshQuotes").textContent = "刷新实时行情";
    alert(e.message);
  }
  $("btnRefreshQuotes").disabled = false;
};

function markQuotesApplied(qs) {
  state.quoteApplied = true;
  $("dataModeBadge").textContent = "实时行情+" + (qs.applied_count || 0) + "只";
  $("dataModeBadge").className = "badge badge-green";
  $("dataBanner").innerHTML =
    "<strong>混合数据模式：</strong>行情字段（PE/PB/市值/换手率）来自<b>腾讯公开行情·实时</b>（" + esc(qs.applied_at || "") + "）；财务指标仍为<b>演示口径</b>。接入扶摇 API 后财务数据切换为真实来源。";
}

/* ---------------- 工具 ---------------- */
function esc(s) {
  return String(s == null ? "" : s).replace(/[&<>"']/g, (ch) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[ch]));
}

$("btnParse").onclick = parseIntent;
$("btnScreen").onclick = runScreen;
$("intentInput").addEventListener("keydown", (ev) => {
  if (ev.key === "Enter" && (ev.ctrlKey || ev.metaKey)) parseIntent();
});

init();
