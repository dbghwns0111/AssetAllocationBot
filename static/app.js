const TRADABLE = ["SPY", "IWM", "VEA", "VWO", "VNQ", "DBC", "IEF", "TLT", "BIL"];
const MODE_LABEL = { offensive: "공격", mixed: "공격 + 일부 방어", defensive: "방어" };

const $ = (id) => document.getElementById(id);
const state = { sig: null, records: [], edited: {} };

const pct = (x, d = 2) => (x == null ? "-" : `${(x * 100).toFixed(d)}%`);
const sgn = (x) => (x > 0 ? "pos" : x < 0 ? "neg" : "");
const usd = (x) => (x == null ? "-" : "$" + Number(x).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }));
const num = (x, d = 4) => Number(x).toLocaleString("en-US", { maximumFractionDigits: d });
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

async function api(path, opts = {}) {
  const res = await fetch(path, { headers: { "Content-Type": "application/json" }, ...opts });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || res.statusText);
  return data;
}

function showError(msg) {
  $("error").textContent = msg;
  $("error").classList.toggle("hidden", !msg);
}

/* ---------- 신호 ---------- */
async function loadSignal(refresh = false) {
  showError("");
  $("signal").innerHTML = '<span class="loading">불러오는 중…</span>';
  const q = new URLSearchParams();
  if ($("partial").checked) q.set("partial", "1");
  if (refresh) q.set("refresh", "1");
  try {
    state.sig = await api("/api/signal?" + q);
    renderSignal();
    renderWeights();
    renderMomentum();
    renderCalc();
  } catch (e) {
    showError("신호 계산 실패: " + e.message);
    $("signal").textContent = "-";
  }
}

function renderSignal() {
  const s = state.sig;
  const notes = [];
  if (!s.canary_on) notes.push(`카나리아 ${s.canary} 모멘텀이 음수 → 전액 방어자산(${s.defensive_asset})`);
  else {
    const bad = s.top.filter((t) => s.assets.find((a) => a.ticker === t).momentum <= 0);
    if (bad.length) notes.push(`상위 4개 중 ${bad.join(", ")} 모멘텀 ≤ 0 → 해당 비중은 ${s.defensive_asset}로 대체`);
    else notes.push(`카나리아 양호 → 공격자산 상위 4개(${s.top.join(", ")})에 25%씩`);
  }
  if (s.partial) notes.push("⚠ 진행 중인 이번 달 가격으로 계산한 미리보기입니다. 실제 리밸런싱은 월말 확정 신호를 사용하세요.");

  $("signal").innerHTML = `
    <div class="sig-head">
      <span class="sig-month">${s.apply_month} 적용</span>
      <span class="mode ${s.mode}">${MODE_LABEL[s.mode]}</span>
    </div>
    <dl class="kv">
      <dt>신호 기준일</dt><dd>${s.asof}${s.partial ? ' <span class="tag">미확정</span>' : ""}</dd>
      <dt>카나리아 (${s.canary})</dt><dd class="${sgn(s.canary_momentum)}">${pct(s.canary_momentum)}</dd>
      <dt>방어자산 선택</dt><dd>${s.defensive_asset} <span class="muted">(BIL vs IEF 중 모멘텀 상위)</span></dd>
      <dt>최신 가격일</dt><dd>${s.price_date}</dd>
    </dl>
    ${notes.map((n) => `<div class="note">${esc(n)}</div>`).join("")}`;
}

function renderWeights() {
  const s = state.sig;
  $("weights").innerHTML = Object.entries(s.weights)
    .map(([t, w]) => `
      <div class="w-row">
        <div><div class="tk">${t}</div></div>
        <div><div class="nm">${esc(s.names[t])}</div><div class="w-bar"><span style="width:${w * 100}%"></span></div></div>
        <div class="pct">${pct(w, 0)}</div>
      </div>`)
    .join("");
}

function renderMomentum() {
  const s = state.sig;
  const order = [...s.ranking.map((t) => s.assets.find((a) => a.ticker === t)),
    ...s.assets.filter((a) => !s.ranking.includes(a.ticker)).sort((a, b) => (a.ticker === "TIP" ? -1 : b.momentum - a.momentum))];
  $("momentum").innerHTML = `
    <tr><th>종목</th><th class="l">구분</th><th>1개월</th><th>3개월</th><th>6개월</th><th>12개월</th><th>13612U</th><th>순위</th><th>현재가</th></tr>
    ${order.map((a) => {
      const sel = s.weights[a.ticker] != null;
      return `<tr class="${sel ? "hl" : ""}">
        <td><b>${a.ticker}</b> <span class="muted">${esc(a.name)}</span>${sel ? '<span class="tag">편입</span>' : ""}</td>
        <td class="l muted">${a.role}</td>
        <td class="${sgn(a.r1)}">${pct(a.r1)}</td><td class="${sgn(a.r3)}">${pct(a.r3)}</td>
        <td class="${sgn(a.r6)}">${pct(a.r6)}</td><td class="${sgn(a.r12)}">${pct(a.r12)}</td>
        <td class="${sgn(a.momentum)}"><b>${pct(a.momentum)}</b></td>
        <td>${a.rank ?? "-"}</td>
        <td>${usd(s.prices[a.ticker])}</td>
      </tr>`;
    }).join("")}`;
}

/* ---------- 계산기 ---------- */
function lastRecord() {
  return state.records[0];
}

function prefillFromLastRecord() {
  const r = lastRecord();
  const cur = {};
  if (r) {
    r.holdings.forEach((h) => (cur[h.ticker] = h.shares));
    $("cash").value = (r.cash ?? 0).toFixed(2);
  }
  state.current = cur;
}

function renderCalc() {
  const s = state.sig;
  if (!s) return;
  if (!state.current) prefillFromLastRecord();
  else readRows().forEach((r) => (state.current[r.t] = r.cur)); // 다시 그려도 입력값 유지
  state.edited = {};
  $("calc").innerHTML = `
    <tr><th>종목</th><th>현재가</th><th>현재 보유</th><th>현재 평가액</th><th>현재 비중</th><th>목표 비중</th><th>목표 수량</th><th>매매</th><th>체결 후 보유</th><th>체결가</th></tr>
    ${TRADABLE.map((t) => `
      <tr data-t="${t}">
        <td><b>${t}</b></td>
        <td>${usd(s.prices[t])}</td>
        <td><input type="number" class="cur" min="0" step="any" value="${state.current[t] ?? 0}"></td>
        <td class="cur-val"></td>
        <td class="cur-w"></td>
        <td>${s.weights[t] ? pct(s.weights[t], 0) : '<span class="muted">-</span>'}</td>
        <td class="tgt"></td>
        <td class="delta"></td>
        <td><input type="number" class="after" min="0" step="any"></td>
        <td><input type="number" class="px" min="0" step="0.01" value="${s.prices[t].toFixed(2)}"></td>
      </tr>`).join("")}`;
  recalc();
}

function readRows() {
  return [...$("calc").querySelectorAll("tr[data-t]")].map((tr) => ({
    tr,
    t: tr.dataset.t,
    cur: parseFloat(tr.querySelector(".cur").value) || 0,
    afterEl: tr.querySelector(".after"),
    px: parseFloat(tr.querySelector(".px").value) || 0,
  }));
}

function recalc() {
  const s = state.sig;
  const frac = $("fractional").checked;
  const rows = readRows();
  const cash = parseFloat($("cash").value) || 0;
  const deposit = parseFloat($("deposit").value) || 0;
  const invested = rows.reduce((a, r) => a + r.cur * s.prices[r.t], 0);
  const total = invested + cash + deposit;

  rows.forEach((r) => {
    const price = s.prices[r.t];
    const w = s.weights[r.t] || 0;
    const raw = (total * w) / price;
    const tgt = frac ? Math.floor(raw * 10000) / 10000 : Math.floor(raw);
    const curVal = r.cur * price;
    r.tr.querySelector(".cur-val").textContent = curVal ? usd(curVal) : "-";
    r.tr.querySelector(".cur-w").textContent = total && curVal ? pct(curVal / total, 1) : "-";
    r.tr.querySelector(".tgt").textContent = num(tgt);
    if (!state.edited[r.t]) r.afterEl.value = tgt;
    const after = parseFloat(r.afterEl.value) || 0;
    const d = after - r.cur;
    const cell = r.tr.querySelector(".delta");
    cell.className = "delta " + (d > 0 ? "buy" : d < 0 ? "sell" : "muted");
    cell.textContent = d > 0 ? `매수 ${num(d)}` : d < 0 ? `매도 ${num(-d)}` : "유지";
    r.tr.classList.toggle("dim", !w && !r.cur && !after);
    r.tr.classList.toggle("hl", !!w);
  });

  // 체결 후 잔여 현금 = 현금 + 입출금 + Σ(매도 - 매수) × 체결가
  const after = calcAfter();
  const tradeCash = readRows().reduce((a, r) => a + (r.cur - (parseFloat(r.afterEl.value) || 0)) * r.px, 0);
  const remain = cash + deposit + tradeCash;
  $("calc-summary").innerHTML = `
    <div><span class="muted">현재 총자산</span><br><b>${usd(total)}</b></div>
    <div><span class="muted">체결 후 주식 평가액</span><br><b>${usd(after.value)}</b></div>
    <div><span class="muted">체결 후 잔여 현금</span><br><b class="${remain < 0 ? "pos" : ""}">${usd(remain)}</b>${remain < 0 ? ' <span class="pos">현금 부족</span>' : ""}</div>`;
  state.remain = remain;
}

function calcAfter() {
  const holdings = readRows()
    .map((r) => ({ ticker: r.t, shares: parseFloat(r.afterEl.value) || 0, price: r.px }))
    .filter((h) => h.shares > 0)
    .map((h) => ({ ...h, value: +(h.shares * h.price).toFixed(2) }));
  return { holdings, value: holdings.reduce((a, h) => a + h.value, 0) };
}

async function saveRecord() {
  const s = state.sig;
  if (s.partial && !confirm("미확정(당월 미리보기) 신호입니다. 그래도 저장할까요?")) return;
  const { holdings, value } = calcAfter();
  const remain = state.remain;
  const body = {
    rebalance_date: $("rb-date").value,
    apply_month: s.apply_month,
    signal_asof: s.asof,
    mode: s.mode,
    canary_momentum: s.canary_momentum,
    weights: s.weights,
    holdings: holdings.map((h) => ({ ...h, weight: value + remain ? h.value / (value + remain) : 0 })),
    cash: +remain.toFixed(2),
    total_value: +(value + remain).toFixed(2),
    memo: $("memo").value,
  };
  try {
    await api("/api/records", { method: "POST", body: JSON.stringify(body) });
    $("memo").value = "";
    $("deposit").value = 0;
    await loadRecords();
    state.current = null;
    renderCalc();
    alert("기록을 저장했습니다.");
  } catch (e) {
    showError("저장 실패: " + e.message);
  }
}

/* ---------- 기록 ---------- */
async function loadRecords() {
  state.records = await api("/api/records");
  renderRecords();
}

function renderRecords() {
  const rs = state.records;
  if (!rs.length) {
    $("records").innerHTML = '<tr><td class="muted">아직 기록이 없습니다. 위 계산기에서 리밸런싱 후 저장하세요.</td></tr>';
    return;
  }
  $("records").innerHTML = `
    <tr><th>리밸런싱 일자</th><th class="l">적용 월</th><th class="l">모드</th><th class="l">보유 종목 (수량 @ 체결가)</th><th>현금</th><th>총자산</th><th>직전 대비</th><th class="l">메모</th><th></th></tr>
    ${rs.map((r, i) => {
      const prev = rs[i + 1];
      const chg = prev && prev.total_value ? r.total_value / prev.total_value - 1 : null;
      return `<tr>
        <td>${r.rebalance_date}</td>
        <td class="l">${r.apply_month ?? "-"}</td>
        <td class="l"><span class="mode ${r.mode}" style="font-size:12px;padding:2px 8px">${MODE_LABEL[r.mode] ?? r.mode}</span></td>
        <td class="hold-list">${r.holdings.map((h) => `<b>${h.ticker}</b> ${num(h.shares)} @ ${usd(h.price)}`).join("<br>") || "-"}</td>
        <td>${usd(r.cash)}</td>
        <td><b>${usd(r.total_value)}</b></td>
        <td class="${sgn(chg)}">${pct(chg)}</td>
        <td class="l"><input type="text" class="memo-edit" data-id="${r.id}" value="${esc(r.memo)}"></td>
        <td><button class="btn small danger" data-del="${r.id}">삭제</button></td>
      </tr>`;
    }).join("")}`;
}

/* ---------- 신호 이력 ---------- */
async function loadHistory() {
  try {
    const rows = await api("/api/history?months=24");
    $("history").innerHTML = `
      <tr><th>적용 월</th><th class="l">신호 기준일</th><th class="l">모드</th><th>TIP 모멘텀</th><th class="l">편입 종목</th><th>해당 월 수익률</th></tr>
      ${rows.map((h) => `<tr>
        <td><b>${h.apply_month}</b></td>
        <td class="l muted">${h.asof}</td>
        <td class="l"><span class="mode ${h.mode}" style="font-size:12px;padding:2px 8px">${MODE_LABEL[h.mode]}</span></td>
        <td class="${sgn(h.canary_momentum)}">${pct(h.canary_momentum)}</td>
        <td class="l">${Object.entries(h.weights).map(([t, w]) => `${t} ${pct(w, 0)}`).join(", ")}</td>
        <td class="${sgn(h.next_return)}">${pct(h.next_return)}${h.next_partial ? ' <span class="tag">진행중</span>' : ""}</td>
      </tr>`).join("")}`;
  } catch (e) {
    $("history").innerHTML = `<tr><td class="muted">이력 계산 실패: ${esc(e.message)}</td></tr>`;
  }
}

/* ---------- 이벤트 ---------- */
$("rb-date").value = new Date().toLocaleDateString("sv-SE"); // YYYY-MM-DD (로컬)
$("refresh").onclick = () => loadSignal(true).then(loadHistory);
$("partial").onchange = () => loadSignal();
$("save").onclick = saveRecord;
["cash", "deposit"].forEach((id) => ($(id).oninput = recalc));
$("fractional").onchange = () => { state.edited = {}; recalc(); };
$("calc").addEventListener("input", (e) => {
  if (e.target.classList.contains("after")) state.edited[e.target.closest("tr").dataset.t] = true;
  if (e.target.classList.contains("cur")) state.edited = {};
  recalc();
});
$("records").addEventListener("click", async (e) => {
  const id = e.target.dataset.del;
  if (!id || !confirm("이 기록을 삭제할까요?")) return;
  await api(`/api/records/${id}`, { method: "DELETE" });
  await loadRecords();
});
$("records").addEventListener("change", async (e) => {
  if (!e.target.classList.contains("memo-edit")) return;
  await api(`/api/records/${e.target.dataset.id}`, { method: "PATCH", body: JSON.stringify({ memo: e.target.value }) });
});

(async () => {
  try { await loadRecords(); } catch (e) { showError("기록 불러오기 실패: " + e.message); }
  await loadSignal();
  loadHistory();
})();
