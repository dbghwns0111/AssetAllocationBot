/* HAA Allocation — 프론트엔드 (프레임워크 없음)
 *
 * 화면: 이번 달(신호) / 리밸런싱(계산기 + 저장) / 기록(내 리밸런싱 + 전략 신호 이력)
 * 상태 변경 요청은 api() 를 통해서만 보낸다 — X-CSRF-Token 자동 부여, 401 이면 로그인으로.
 */
'use strict';

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const CSRF = document.querySelector('meta[name="csrf-token"]')?.content || '';
const TRADABLE = ['SPY', 'IWM', 'VEA', 'VWO', 'VNQ', 'DBC', 'IEF', 'TLT', 'BIL'];
const MODE = {
  offensive: { title: '공격 모드', icon: 'i-offensive' },
  mixed:     { title: '공격 + 일부 방어', icon: 'i-mixed' },
  defensive: { title: '방어 모드', icon: 'i-defensive' },
};

const S = {
  sig: null, partial: false, records: [], hist: null,
  view: 'signal', recSub: 'mine', charts: {},
  rb: null,          // { cur, after, px, edited, cash, deposit } — 계산기 입력의 원본
  rbPrefilled: false,
};

/* ── 포맷 ────────────────────────────────────────────────────────────────── */
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const pct = (x, d = 2, sign = true) => x == null ? '-' : `${sign && x > 0 ? '+' : ''}${(x * 100).toFixed(d)}%`;
const usd = (x) => x == null ? '-' : `${x < 0 ? '−' : ''}$${Math.abs(x).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const num = (x, d = 4) => Number(x).toLocaleString('en-US', { maximumFractionDigits: d });
const tri = (x) => x > 0 ? '<span class="tri pos">▲</span>' : x < 0 ? '<span class="tri neg">▼</span>' : '';
const tcolor = (t) => `var(--t-${t})`;
const cssVar = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const monthLabel = (ym) => { const [y, m] = ym.split('-'); return `${y}년 ${Number(m)}월`; };
const todayStr = () => new Date().toLocaleDateString('sv-SE');
const fnum = (v) => { const x = parseFloat(v); return Number.isFinite(x) ? x : 0; };

/* ── API ─────────────────────────────────────────────────────────────────── */
async function api(path, opts = {}) {
  const method = (opts.method || 'GET').toUpperCase();
  const headers = { 'Content-Type': 'application/json' };
  if (method !== 'GET') headers['X-CSRF-Token'] = CSRF;
  const res = await fetch(path, { ...opts, method, headers });
  if (res.status === 401) { location.href = '/login'; throw new Error('로그인이 필요합니다.'); }
  let data = null;
  try { data = await res.json(); } catch { /* 빈 응답 */ }
  if (!res.ok) throw new Error((data && data.error) || `요청 실패 (${res.status})`);
  return data;
}

/* ── 토스트 · 다이얼로그 · 버튼 잠금 ──────────────────────────────────────── */
function toast(msg, type = 'ok') {
  const el = document.createElement('div');
  el.className = `toast ${type === 'err' ? 'err' : ''}`;
  el.innerHTML = `<svg><use href="#${type === 'err' ? 'i-alert' : 'i-check'}"/></svg><span></span>`;
  el.querySelector('span').textContent = msg;
  $('#toasts').appendChild(el);
  setTimeout(() => el.remove(), type === 'err' ? 6000 : 3000);
}

function confirmDialog({ title, body, okText = '확인', danger = false }) {
  const dlg = $('#dlg');
  $('#dlg-title').textContent = title;
  $('#dlg-content').textContent = body;
  const ok = $('#dlg-ok');
  ok.textContent = okText;
  ok.className = `btn ${danger ? 'btn-danger' : 'btn-primary'}`;
  if (typeof dlg.showModal !== 'function') return Promise.resolve(window.confirm(`${title}\n\n${body}`));
  return new Promise((resolve) => {
    const done = (v) => { dlg.close(); resolve(v); };
    ok.onclick = () => done(true);
    $('#dlg-cancel').onclick = () => done(false);
    dlg.oncancel = (e) => { e.preventDefault(); done(false); };
    dlg.showModal();
    ok.focus();
  });
}

// 요청이 끝날 때까지 버튼을 잠근다 (연타로 인한 중복 요청 방지)
async function busy(btn, fn) {
  if (!btn || btn.classList.contains('busy')) return;
  btn.classList.add('busy');
  try { return await fn(); } finally { btn.classList.remove('busy'); }
}

/* ── 툴팁 ────────────────────────────────────────────────────────────────── */
const tipEl = () => $('#tip');
function showTip(html, x, y) {
  const el = tipEl();
  el.innerHTML = html;
  el.classList.add('on');
  const r = el.getBoundingClientRect();
  let left = x + 14, top = y + 14;
  if (left + r.width > innerWidth - 8) left = x - r.width - 14;
  if (top + r.height > innerHeight - 8) top = y - r.height - 14;
  el.style.left = `${Math.max(8, left)}px`;
  el.style.top = `${Math.max(8, top)}px`;
}
function hideTip() { tipEl().classList.remove('on'); }
function bindTip(el, htmlFn) {
  el.addEventListener('pointermove', (e) => { if (e.pointerType === 'mouse') showTip(htmlFn(), e.clientX, e.clientY); });
  el.addEventListener('pointerleave', hideTip);
  el.addEventListener('click', (e) => {   // 터치: 탭하면 표시
    const r = el.getBoundingClientRect();
    showTip(htmlFn(), e.clientX || r.left + r.width / 2, e.clientY || r.top);
  });
}
document.addEventListener('pointerdown', (e) => { if (!e.target.closest('[data-tip]')) hideTip(); });
addEventListener('scroll', hideTip, { passive: true });

/* ── 라우팅 ──────────────────────────────────────────────────────────────── */
function setView(view, push = true) {
  // "#records/history" 처럼 하위 탭까지 지정 가능
  const [v, sub] = String(view || '').split('/');
  view = v;
  if (sub === 'mine' || sub === 'history') S.recSub = sub;
  if (!['signal', 'rebalance', 'records'].includes(view)) view = 'signal';
  S.view = view;
  $$('.view').forEach((v) => v.classList.toggle('on', v.id === `view-${view}`));
  $$('[data-view]').forEach((b) => { if (b.dataset.view === view) b.setAttribute('aria-current', 'page'); else b.removeAttribute('aria-current'); });
  const hash = view === 'records' ? `#records/${S.recSub}` : `#${view}`;
  if (push && location.hash !== hash) history.replaceState(null, '', hash);
  scrollTo({ top: 0 });
  hideTip();
  if (view === 'records') renderRecordsView();
}

/* ══ 이번 달 ════════════════════════════════════════════════════════════════ */
async function loadSignal(refresh = false) {
  const q = new URLSearchParams();
  if (S.partial) q.set('partial', '1');
  if (refresh) q.set('refresh', '1');
  S.sig = await api(`/api/signal?${q}`);
  renderSignal();
  renderRebalance();
}

function reasonText(s) {
  const mom = Object.fromEntries(s.assets.map((a) => [a.ticker, a.momentum]));
  if (!s.canary_on) return `카나리아 TIP 모멘텀이 ${pct(s.canary_momentum)}로 0 이하라서, 이번 달은 전액 ${s.defensive_asset}(으)로 방어합니다.`;
  const bad = s.top.filter((t) => mom[t] <= 0);
  if (bad.length) return `상위 4개 중 ${bad.join(', ')}의 모멘텀이 0 이하라서 그 몫은 ${s.defensive_asset}(으)로 대체합니다.`;
  return `카나리아가 양호해 공격자산 상위 4개(${s.top.join(', ')})에 25%씩 투자합니다.`;
}

function renderSignal() {
  const s = S.sig;
  const m = MODE[s.mode];
  const pills = [
    `<span class="pill"><svg><use href="#i-clock"/></svg>기준 <b>${s.asof}</b> 종가</span>`,
    `<span class="pill">가격 ${s.price_date} · ${s.fetched_at.slice(11, 16)} 조회</span>`,
  ];
  if (s.partial) pills.push('<span class="pill warn"><svg><use href="#i-alert"/></svg>미확정 · 당월 미리보기</span>');
  if (s.stale) pills.push('<span class="pill warn"><svg><use href="#i-alert"/></svg>가격 조회 실패 · 이전 데이터</span>');
  if (s.next_hint) pills.push(`<span class="pill warn"><svg><use href="#i-clock"/></svg>${esc(s.next_hint)}</span>`);

  const hero = $('#hero');
  hero.className = `card hero mode-${s.mode}`;
  hero.innerHTML = `
    <div class="hero-status">
      <div class="mode-icon"><svg><use href="#${m.icon}"/></svg></div>
      <div>
        <div class="eyebrow">${monthLabel(s.apply_month)} 포트폴리오</div>
        <h1 class="hero-title">${m.title}</h1>
      </div>
    </div>
    <p class="hero-desc">${esc(reasonText(s))}</p>
    <div class="hero-meta">${pills.join('')}</div>
    <div class="toggle-row">
      <label class="switch"><input type="checkbox" id="partial-toggle" ${S.partial ? 'checked' : ''}><span class="track"></span>진행 중인 달 가격으로 미리보기</label>
      <a class="btn btn-primary btn-sm" href="#rebalance" data-goto="rebalance" style="text-decoration:none">리밸런싱 하기 →</a>
    </div>`;
  $('#partial-toggle').onchange = async (e) => {
    S.partial = e.target.checked;
    try { await loadSignal(); } catch (err) { toast(err.message, 'err'); }
  };
  hero.querySelector('[data-goto]').onclick = (e) => { e.preventDefault(); setView('rebalance'); };

  renderAlloc();
  renderCanary();
  renderChanges();
  renderMomentum();
}

function renderAlloc() {
  const s = S.sig;
  const entries = Object.entries(s.weights);
  $('#alloc-sub').textContent = entries.length === 1 ? '1종목 100%' : `${entries.length}종목 · ${entries.map(([, w]) => pct(w, 0, false)).join(' / ')}`;

  // 도넛: 원주 위에 dasharray 로 구간을 그리고, 구간 사이 2px 간격
  const R = 80, C = 2 * Math.PI * R, GAP = entries.length > 1 ? 2.5 : 0;
  let offset = 0;
  const segs = entries.map(([t, w]) => {
    const len = w * C;
    const seg = `<circle class="seg" data-t="${t}" cx="100" cy="100" r="${R}" fill="none" stroke="${tcolor(t)}" stroke-width="26"
      stroke-dasharray="${Math.max(len - GAP, 0.1)} ${C - Math.max(len - GAP, 0.1)}" stroke-dashoffset="${-offset}"></circle>`;
    offset += len;
    return seg;
  }).join('');
  const names = s.names;
  $('#alloc').innerHTML = `
    <div class="donut" id="donut">
      <svg viewBox="0 0 200 200" role="img" aria-label="목표 비중 도넛 차트">
        <circle cx="100" cy="100" r="${R}" fill="none" stroke="var(--surface-3)" stroke-width="26"></circle>${segs}
      </svg>
      <div class="donut-center"><div class="big">${entries.length}</div><div class="small">종목</div></div>
    </div>
    <ul class="legend">
      ${entries.map(([t, w]) => `
        <li data-t="${t}"><span class="sw" style="background:${tcolor(t)}"></span>
          <div class="lg-name"><b>${t}</b><span>${esc(names[t])}</span></div>
          <div class="lg-val">${pct(w, 0, false)}</div></li>`).join('')}
    </ul>`;

  const donut = $('#donut');
  const hot = (t) => {
    donut.classList.toggle('hovering', !!t);
    $$('.seg', donut).forEach((c) => c.classList.toggle('hot', c.dataset.t === t));
    $$('.legend li').forEach((li) => li.classList.toggle('hot', li.dataset.t === t));
  };
  $$('.seg, .legend li', $('#alloc')).forEach((el) => {
    el.addEventListener('pointerenter', () => hot(el.dataset.t));
    el.addEventListener('pointerleave', () => hot(null));
  });
}

function renderCanary() {
  const s = S.sig;
  const v = s.canary_momentum;
  const dom = Math.max(0.06, Math.abs(v) * 1.4);
  const w = Math.min(50, (Math.abs(v) / dom) * 50);
  const tip = s.assets.find((a) => a.ticker === 'TIP');
  $('#canary').innerHTML = `
    <div class="canary-top">
      <div class="canary-val tnum">${pct(v)}</div>
      ${s.canary_on
        ? '<span class="state ok"><svg><use href="#i-check"/></svg>정상 · 공격 가능</span>'
        : '<span class="state risk"><svg><use href="#i-alert"/></svg>경고 · 방어 전환</span>'}
    </div>
    <div class="meter" aria-hidden="true"><div class="zero"></div><div class="fill ${v >= 0 ? 'pos' : 'neg'}" style="width:${w}%"></div></div>
    <div class="meter-scale tnum"><span>${pct(-dom, 0)}</span><span>0</span><span>${pct(dom, 0)}</span></div>
    <div class="hero-meta" style="margin-top:12px">
      ${['r1', 'r3', 'r6', 'r12'].map((k) => `<span class="pill">${k.slice(1)}개월 <b class="tnum">${pct(tip[k], 1)}</b></span>`).join('')}
    </div>`;
}

function renderChanges() {
  const s = S.sig;
  const prev = Object.keys(s.prev.weights);
  const cur = Object.keys(s.weights);
  const kept = cur.filter((t) => prev.includes(t));
  $('#chg-sub').textContent = `${monthLabel(s.prev.apply_month)} → ${monthLabel(s.apply_month)}`;
  const chips = (list, cls) => list.map((t) => `<span class="chip ${cls}"><span class="sw" style="background:${tcolor(t)}"></span>${t}</span>`).join('');
  const rows = [];
  if (s.added.length) rows.push(`<div class="chg-row"><span class="chg-label">새로 편입</span>${chips(s.added, 'in')}</div>`);
  if (s.removed.length) rows.push(`<div class="chg-row"><span class="chg-label">제외</span>${chips(s.removed, 'out')}</div>`);
  if (kept.length) rows.push(`<div class="chg-row"><span class="chg-label">유지</span>${chips(kept, '')}</div>`);
  if (!s.added.length && !s.removed.length) rows.unshift('<div class="chg-arrow"><span class="state ok"><svg><use href="#i-check"/></svg>지난달과 같은 종목</span><span class="muted">비중만 확인하세요</span></div>');
  $('#changes').innerHTML = rows.join('');
}

function momTip(a) {
  return `<div class="tip-title"><span class="sw" style="background:${tcolor(a.ticker)}"></span>${a.ticker} <span class="muted" style="font-weight:500">${esc(a.name)}</span></div>
    ${['r1', 'r3', 'r6', 'r12'].map((k) => `<div class="tip-row"><span>${k.slice(1)}개월</span><b>${pct(a[k])}</b></div>`).join('')}
    <div class="tip-row" style="margin-top:4px;padding-top:4px;border-top:1px solid var(--line)"><span>13612U</span><b>${pct(a.momentum)}</b></div>`;
}

function renderMomentum() {
  const s = S.sig;
  const by = Object.fromEntries(s.assets.map((a) => [a.ticker, a]));
  const order = [...s.ranking, 'TIP', 'BIL'];
  const dom = Math.max(...order.map((t) => Math.abs(by[t].momentum))) || 1;
  $('#momentum').innerHTML = order.map((t, i) => {
    const a = by[t];
    const pick = t in s.weights;
    const w = (Math.abs(a.momentum) / dom) * 50;
    const role = t === 'TIP' ? '카나리아' : (t === 'BIL' || t === 'IEF') ? '방어 후보' : '';
    return `<div class="mom-row ${pick ? 'pick' : ''} ${i === s.ranking.length ? 'sep' : ''}" data-t="${t}" data-tip tabindex="0">
      <div class="mom-rank">${a.rank ?? '·'}</div>
      <div class="mom-name"><span class="sw" style="background:${tcolor(t)};width:8px;height:8px;border-radius:3px;flex-shrink:0"></span><b>${t}</b>
        ${pick ? '<em class="badge-pick">편입</em>' : ''}${role ? `<em class="badge-role">${role}</em>` : ''}<span>${esc(a.name)}</span></div>
      <div class="mom-track"><div class="mom-bar ${a.momentum >= 0 ? 'pos' : 'neg'}" style="width:${w}%"></div></div>
      <div class="mom-val">${tri(a.momentum)}${pct(a.momentum)}</div>
    </div>`;
  }).join('');
  $$('#momentum .mom-row').forEach((row) => bindTip(row, () => momTip(by[row.dataset.t])));

  $('#momentum-table').innerHTML = `<table class="tbl">
    <thead><tr><th>종목</th><th>구분</th><th>1개월</th><th>3개월</th><th>6개월</th><th>12개월</th><th>13612U</th><th>순위</th><th>현재가</th></tr></thead>
    <tbody>${order.map((t) => { const a = by[t]; return `<tr class="${t in s.weights ? 'pick' : ''}">
      <td><b>${t}</b> <span class="muted">${esc(a.name)}</span></td><td>${a.role}</td>
      <td>${pct(a.r1)}</td><td>${pct(a.r3)}</td><td>${pct(a.r6)}</td><td>${pct(a.r12)}</td>
      <td><b>${pct(a.momentum)}</b></td><td>${a.rank ?? '-'}</td><td>${usd(s.prices[t])}</td></tr>`; }).join('')}</tbody></table>`;
}

/* ══ 리밸런싱 ═══════════════════════════════════════════════════════════════ */
function latestRecord() { return S.records[0] || null; }

function prefillRebalance() {
  const r = latestRecord();
  const cur = {};
  (r?.holdings || []).forEach((h) => { cur[h.ticker] = h.shares; });
  S.rb = { cur, after: {}, px: {}, edited: {}, cash: r ? r.cash : 0, deposit: 0 };
  $('#rb-cash').value = (S.rb.cash || 0).toFixed(2);
  $('#rb-deposit').value = 0;
  $('#rb-prev').textContent = r
    ? `직전 기록 ${r.rebalance_date} (${r.apply_month || '-'} 적용) 의 보유 수량과 현금을 불러왔습니다.`
    : '첫 기록입니다. 현재 보유 수량과 현금을 입력하세요.';
  S.rbPrefilled = true;
}

function renderRebalance() {
  const s = S.sig;
  if (!s || !S.rbPrefilled) return;
  const showAll = $('#rb-all').checked;
  $('#rb-signal').textContent = `${monthLabel(s.apply_month)} 신호 · ${MODE[s.mode].title}${s.partial ? ' (미리보기)' : ''} · 가격 ${s.price_date}`;
  TRADABLE.forEach((t) => { if (S.rb.px[t] == null) S.rb.px[t] = +s.prices[t].toFixed(2); });

  const rows = TRADABLE.filter((t) => showAll || s.weights[t] || fnum(S.rb.cur[t]) > 0);
  $('#orders').innerHTML = rows.map((t) => `
    <div class="order" data-t="${t}">
      <div class="order-id"><span class="sw" style="background:${tcolor(t)}"></span>
        <div style="min-width:0"><b>${t}</b><small>${esc(s.names[t])} · ${usd(s.prices[t])}</small></div></div>
      <span class="action hold" data-k="action">유지</span>
      <div class="order-meta" data-k="meta"></div>
      <div class="order-fields">
        <label>현재 보유<input class="input sm" type="number" inputmode="decimal" min="0" step="any" data-f="cur" value="${S.rb.cur[t] ?? 0}"></label>
        <label>체결 후 보유<input class="input sm" type="number" inputmode="decimal" min="0" step="any" data-f="after"></label>
        <label>체결가 (USD)<input class="input sm" type="number" inputmode="decimal" min="0" step="0.01" data-f="px" value="${S.rb.px[t]}"></label>
      </div>
    </div>`).join('') || '<div class="empty">표시할 종목이 없습니다.</div>';
  recalc();
}

function recalc() {
  const s = S.sig;
  if (!s || !S.rb) return;
  const rb = S.rb;
  const frac = $('#rb-fractional').checked;
  rb.cash = fnum($('#rb-cash').value);
  rb.deposit = fnum($('#rb-deposit').value);
  const invested = TRADABLE.reduce((a, t) => a + fnum(rb.cur[t]) * s.prices[t], 0);
  const total = invested + rb.cash + rb.deposit;

  let buy = 0, sell = 0;
  const afterVal = {};
  TRADABLE.forEach((t) => {
    const w = s.weights[t] || 0;
    const raw = total > 0 ? (total * w) / s.prices[t] : 0;
    const target = frac ? Math.floor(raw * 10000) / 10000 : Math.floor(raw);
    if (!rb.edited[t]) rb.after[t] = target;
    const cur = fnum(rb.cur[t]);
    const after = fnum(rb.after[t]);
    const px = fnum(rb.px[t]) || s.prices[t];
    const d = after - cur;
    if (d > 0) buy += d * px; else sell += -d * px;
    if (after > 0) afterVal[t] = after * px;

    const row = $(`.order[data-t="${t}"]`);
    if (!row) return;
    row.classList.toggle('idle', !w && !cur && !after);
    const act = row.querySelector('[data-k="action"]');
    act.className = `action ${d > 0 ? 'buy' : d < 0 ? 'sell' : 'hold'}`;
    act.textContent = d > 0 ? `매수 ${num(d)}주` : d < 0 ? `매도 ${num(-d)}주` : '유지';
    row.querySelector('[data-k="meta"]').innerHTML =
      `<span>목표 <b>${pct(w, 0, false)}</b></span><span>목표 수량 <b>${num(target)}주</b></span><span>체결 후 <b>${usd(after * px)}</b></span>`;
    const afterInput = row.querySelector('[data-f="after"]');
    if (document.activeElement !== afterInput) afterInput.value = rb.after[t];
  });

  const remain = rb.cash + rb.deposit + sell - buy;
  $('#sum-total').textContent = usd(total);
  $('#sum-buy').textContent = usd(buy);
  $('#sum-sell').textContent = usd(sell);
  const cashEl = $('#sum-cash');
  cashEl.textContent = usd(remain) + (remain < -0.005 ? ' 부족' : '');
  cashEl.style.color = remain < -0.005 ? 'var(--up)' : '';

  const parts = Object.entries(afterVal);
  if (remain > 0.005) parts.push(['CASH', remain]);
  const sum = parts.reduce((a, [, v]) => a + v, 0) || 1;
  $('#sum-bar').innerHTML = parts.map(([t, v]) => `<span style="width:${(v / sum) * 100}%;background:${tcolor(t)}" title="${t}"></span>`).join('');
  $('#sum-legend').innerHTML = parts.map(([t, v]) => `<span><i style="background:${tcolor(t)}"></i>${t === 'CASH' ? '현금' : t} ${pct(v / sum, 1, false)}</span>`).join('');
  S.rbTotals = { buy, sell, remain, total };
}

function onOrderInput(e) {
  const input = e.target.closest('input[data-f]');
  if (!input) return;
  const t = input.closest('.order').dataset.t;
  const f = input.dataset.f;
  S.rb[f][t] = fnum(input.value);
  if (f === 'after') S.rb.edited[t] = true;
  if (f === 'cur') S.rb.edited = {};   // 보유가 바뀌면 목표를 다시 계산
  recalc();
}

async function saveRecord(btn) {
  const s = S.sig;
  const rb = S.rb;
  const date = $('#rb-date').value;
  if (!date) { toast('매매일을 입력하세요.', 'err'); return; }
  const holdings = TRADABLE.map((t) => ({ ticker: t, shares: fnum(rb.after[t]), price: fnum(rb.px[t]) || s.prices[t] }))
    .filter((h) => h.shares > 0);
  const trades = TRADABLE.map((t) => {
    const d = fnum(rb.after[t]) - fnum(rb.cur[t]);
    const px = fnum(rb.px[t]) || s.prices[t];
    return d > 0 ? `매수  ${t}  ${num(d)}주 @ ${usd(px)}` : d < 0 ? `매도  ${t}  ${num(-d)}주 @ ${usd(px)}` : null;
  }).filter(Boolean);
  const { remain } = S.rbTotals;
  const value = holdings.reduce((a, h) => a + h.shares * h.price, 0);

  const lines = [
    `${date} · ${monthLabel(s.apply_month)} 신호 (${MODE[s.mode].title})`,
    '',
    ...(trades.length ? trades : ['매매 없음 (보유 유지)']),
    '',
    `체결 후 총자산  ${usd(value + remain)}`,
    `잔여 현금  ${usd(remain)}`,
  ];
  if (s.partial) lines.unshift('⚠ 미확정(당월 미리보기) 신호입니다.', '');
  if (remain < -0.005) lines.push('⚠ 현금이 부족합니다. 수량을 확인하세요.');
  if (!(await confirmDialog({ title: '이 내용으로 기록할까요?', body: lines.join('\n'), okText: '저장' }))) return;

  await busy(btn, async () => {
    try {
      const res = await api('/api/records', {
        method: 'POST',
        body: JSON.stringify({
          rebalance_date: date, apply_month: s.apply_month, signal_asof: s.asof, mode: s.mode,
          canary_momentum: s.canary_momentum, weights: s.weights, holdings, cash: +remain.toFixed(2),
          memo: $('#rb-memo').value,
        }),
      });
      toast(res.message);
      $('#rb-memo').value = '';
      await loadRecords();
      prefillRebalance();
      renderRebalance();
    } catch (err) { toast(err.message, 'err'); }
  });
}

/* ══ 기록 ═══════════════════════════════════════════════════════════════════ */
async function loadRecords() {
  S.records = await api('/api/records');
  if (S.view === 'records') renderRecordsView();
}

function renderRecordsView() {
  $('#sub-mine').classList.toggle('hidden', S.recSub !== 'mine');
  $('#sub-history').classList.toggle('hidden', S.recSub !== 'history');
  $$('#rec-tabs button').forEach((b) => b.classList.toggle('on', b.dataset.sub === S.recSub));
  if (S.recSub === 'mine') renderRecords();
  else loadHistory();
}

function renderRecords() {
  const rs = S.records;
  const latest = rs[0], prev = rs[1], first = rs[rs.length - 1];
  const delta = (a, b) => (a && b && b.total_value ? a.total_value / b.total_value - 1 : null);
  const d1 = delta(latest, prev), d0 = rs.length > 1 ? delta(latest, first) : null;
  const stat = (label, value, d, note) => `<div class="stat"><div class="stat-label">${label}</div><div class="stat-value tnum">${value}</div>
    <div class="stat-delta ${d > 0 ? 'pos' : d < 0 ? 'neg' : 'muted'}">${d == null ? (note || '&nbsp;') : `${tri(d)} ${pct(d)} ${note || ''}`}</div></div>`;
  $('#rec-stats').innerHTML =
    stat('현재 총자산', latest ? usd(latest.total_value) : '-', d1, '직전 대비') +
    stat('첫 기록 대비', d0 == null ? '-' : pct(d0), null, first ? `${first.rebalance_date}부터 · 입출금 포함` : '') +
    stat('리밸런싱 횟수', `${rs.length}회`, null, latest ? `최근 ${latest.rebalance_date}` : '');

  $('#rec-chart-card').classList.toggle('hidden', rs.length < 2);
  if (rs.length >= 2) {
    const asc = [...rs].reverse();
    lineChart('rec', $('#rec-chart'), asc.map((r) => r.rebalance_date), asc.map((r) => r.total_value), {
      label: '총자산', fmt: usd, tick: (v) => `$${Number(v).toLocaleString('en-US', { maximumFractionDigits: 0 })}`,
    });
  }

  if (!rs.length) {
    $('#timeline').innerHTML = `<div class="empty"><svg><use href="#i-empty"/></svg><b>아직 기록이 없습니다</b>리밸런싱 화면에서 매매 후 기록을 저장하면 여기에 쌓입니다.</div>`;
    return;
  }
  $('#timeline').innerHTML = rs.map((r, i) => {
    const p = rs[i + 1];
    const d = p && p.total_value ? r.total_value / p.total_value - 1 : null;
    const parts = r.holdings.map((h) => [h.ticker, h.value]);
    if (r.cash > 0.005) parts.push(['CASH', r.cash]);
    const sum = parts.reduce((a, [, v]) => a + v, 0) || 1;
    return `<div class="tl-item"><div class="tl-rail"><span class="tl-dot"></span></div><div class="tl-body"><div class="tl-card">
      <div class="tl-head">
        <span class="tl-date">${r.rebalance_date}</span>
        ${r.mode ? `<span class="mode-tag ${r.mode}">${MODE[r.mode]?.title || r.mode}</span>` : ''}
        <span class="muted" style="font-size:12.5px">${r.apply_month ? `${monthLabel(r.apply_month)} 적용` : ''}</span>
        <div class="tl-total"><b>${usd(r.total_value)}</b>${d == null ? '' : `<small class="${d > 0 ? 'stat-delta pos' : d < 0 ? 'stat-delta neg' : 'muted'}">${tri(d)} ${pct(d)}</small>`}</div>
      </div>
      <div class="mini-bar" style="margin-top:12px">${parts.map(([t, v]) => `<span style="width:${(v / sum) * 100}%;background:${tcolor(t)}" title="${t}"></span>`).join('')}</div>
      <div class="tl-holds">
        ${r.holdings.map((h) => `<div class="tl-hold"><span><b>${h.ticker}</b> ${num(h.shares)}주 @ ${usd(h.price)}</span><span>${usd(h.value)}</span></div>`).join('')}
        <div class="tl-hold"><span>현금</span><span>${usd(r.cash)}</span></div>
      </div>
      <div class="tl-foot">
        <input class="input" data-memo="${r.id}" value="${esc(r.memo)}" placeholder="메모" maxlength="500">
        <button class="btn btn-ghost btn-sm" data-del="${r.id}">삭제</button>
      </div>
    </div></div></div>`;
  }).join('');
}

async function loadHistory() {
  if (!S.hist) {
    $('#hist-table').innerHTML = '<div class="skeleton" style="height:240px"></div>';
    try { S.hist = await api('/api/history?months=24'); } catch (err) { $('#hist-table').innerHTML = `<div class="empty">${esc(err.message)}</div>`; return; }
  }
  const asc = [...S.hist].reverse().filter((h) => h.return != null);
  let acc = 1;
  const cum = asc.map((h) => (acc *= 1 + h.return) - 1);
  const total = cum.length ? cum[cum.length - 1] : null;
  $('#hist-total').innerHTML = total == null ? '' : `${tri(total)} ${pct(total)}`;
  // 시작점(0%)을 첫 신호 기준월에 둔다 — 첫 달 수익률부터 그리면 출발선이 안 보임
  const labels = asc.length ? [asc[0].asof.slice(0, 7), ...asc.map((h) => h.apply_month)] : [];
  lineChart('hist', $('#hist-chart'), labels, asc.length ? [0, ...cum] : [], {
    label: '누적 수익률', fmt: (v) => pct(v), tick: (v) => `${Math.round(v * 100)}%`, zero: true,
  });
  $('#hist-table').innerHTML = `<table class="tbl">
    <thead><tr><th>적용 월</th><th>모드</th><th style="text-align:left">편입 종목</th><th>TIP</th><th>해당 월 수익률</th></tr></thead>
    <tbody>${S.hist.map((h) => `<tr>
      <td><b>${h.apply_month}</b></td>
      <td><span class="mode-tag ${h.mode}">${MODE[h.mode].title}</span></td>
      <td style="text-align:left">${Object.entries(h.weights).map(([t, w]) => `<span class="chip" style="padding:2px 8px;font-size:12px;margin:1px"><span class="sw" style="background:${tcolor(t)}"></span>${t}${w !== 0.25 ? ` ${pct(w, 0, false)}` : ''}</span>`).join('')}</td>
      <td>${pct(h.canary_momentum, 1)}</td>
      <td><b>${h.return == null ? '-' : `${tri(h.return)} ${pct(h.return)}`}</b>${h.return_partial ? ' <span class="muted">(진행 중)</span>' : ''}</td>
    </tr>`).join('')}</tbody></table>`;
}

/* ── 차트 (Chart.js) : 단일 시리즈 라인 + 10% 면 채움 + 세로 크로스헤어 툴팁 ── */
const crosshair = {
  id: 'crosshair',
  afterDatasetsDraw(chart) {
    const a = chart.tooltip?.getActiveElements?.();
    if (!a || !a.length) return;
    const x = a[0].element.x, { top, bottom } = chart.chartArea, ctx = chart.ctx;
    ctx.save();
    ctx.strokeStyle = cssVar('--muted'); ctx.globalAlpha = 0.5; ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(x, top); ctx.lineTo(x, bottom); ctx.stroke(); ctx.restore();
  },
};

function lineChart(key, canvas, labels, data, { label, fmt, tick, zero = false }) {
  if (typeof Chart === 'undefined') return;
  S.charts[key]?.destroy();
  const accent = cssVar('--accent'), line = cssVar('--line'), muted = cssVar('--muted'), surface = cssVar('--surface'), ink = cssVar('--ink');
  const ctx = canvas.getContext('2d');
  const grad = ctx.createLinearGradient(0, 0, 0, canvas.parentElement.clientHeight || 240);
  grad.addColorStop(0, `${accent}26`); grad.addColorStop(1, `${accent}00`);
  S.charts[key] = new Chart(canvas, {
    type: 'line',
    data: { labels, datasets: [{
      label, data, borderColor: accent, borderWidth: 2, cubicInterpolationMode: 'monotone', fill: zero ? 'origin' : 'start', backgroundColor: grad,
      pointRadius: data.length <= 12 ? 3 : 0, pointHoverRadius: 5, pointBackgroundColor: accent,
      pointBorderColor: surface, pointBorderWidth: 2, borderCapStyle: 'round', borderJoinStyle: 'round',
    }] },
    options: {
      responsive: true, maintainAspectRatio: false, animation: { duration: 300 },
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: surface, titleColor: ink, bodyColor: ink, borderColor: line, borderWidth: 1,
          padding: 10, displayColors: false, cornerRadius: 10,
          callbacks: { label: (c) => `${label}  ${fmt(c.parsed.y)}` },
        },
      },
      scales: {
        x: { grid: { display: false }, border: { color: line }, ticks: { color: muted, maxRotation: 0, autoSkipPadding: 16, font: { size: 11 } } },
        y: { grid: { color: line }, border: { display: false }, ticks: { color: muted, callback: tick, font: { size: 11 }, maxTicksLimit: 5 } },
      },
    },
    plugins: [crosshair],
  });
}

/* ══ 설정 시트 ══════════════════════════════════════════════════════════════ */
function openSheet(on) {
  $('#sheet').classList.toggle('on', on);
  $('#scrim').classList.toggle('on', on);
  $('#sheet').setAttribute('aria-hidden', on ? 'false' : 'true');
  if (on) loadSystem();
}

async function loadSystem() {
  try {
    const s = await api('/api/system');
    const last = s.last_signal_notify;
    $('#set-telegram').innerHTML = `
      <div class="set-row"><span>상태</span><span class="v"><span class="dot ${s.telegram_enabled ? 'on' : 'off'}"></span>${s.telegram_enabled ? '연결됨' : '미설정'}</span></div>
      ${s.telegram_enabled ? `<div class="set-row"><span>채팅 ID</span><span class="v tnum">${esc(s.telegram_chat)}</span></div>` : ''}
      <div class="set-row"><span>마지막 신호 발송</span><span class="v">${last ? `${esc(last.key)} · ${esc(last.sent_at.replace('T', ' ').slice(0, 16))}` : '-'}</span></div>
      <div class="set-row"><span>다음 자동 점검</span><span class="v tnum">${esc(s.next_runs?.signal_check || '-')}</span></div>
      ${s.telegram_enabled ? '' : '<p class="card-sub" style="margin-top:8px">서버의 .env 에 TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID 를 넣고 재시작하세요.</p>'}`;
  } catch (err) { $('#set-telegram').textContent = err.message; }
}

/* ── 테마 ────────────────────────────────────────────────────────────────── */
function effectiveTheme() {
  const t = document.documentElement.dataset.theme;
  if (t === 'light' || t === 'dark') return t;
  return matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}
function setTheme(mode) {
  if (mode === 'system') delete document.documentElement.dataset.theme;
  else document.documentElement.dataset.theme = mode;
  try { if (mode === 'system') localStorage.removeItem('haa-theme'); else localStorage.setItem('haa-theme', mode); } catch { /* 저장 불가 환경 */ }
  syncThemeSeg();
  rerenderCharts();
}
function syncThemeSeg() {
  const cur = document.documentElement.dataset.theme || 'system';
  $$('#theme-seg button').forEach((b) => b.classList.toggle('on', b.dataset.themeSet === cur));
}
function rerenderCharts() {
  if (S.view === 'records') renderRecordsView();
}
matchMedia('(prefers-color-scheme: dark)').addEventListener?.('change', rerenderCharts);

/* ══ 이벤트 & 시작 ══════════════════════════════════════════════════════════ */
function bindEvents() {
  $$('[data-view]').forEach((b) => b.addEventListener('click', () => setView(b.dataset.view)));
  addEventListener('hashchange', () => setView(location.hash.slice(1), false));

  $('#btn-refresh').addEventListener('click', async (e) => {
    const btn = e.currentTarget;
    if (btn.classList.contains('spinning')) return;
    btn.classList.add('spinning');
    try { await loadSignal(true); S.hist = null; if (S.view === 'records') renderRecordsView(); toast('최신 가격으로 다시 계산했습니다.'); }
    catch (err) { toast(err.message, 'err'); }
    finally { btn.classList.remove('spinning'); }
  });
  $('#btn-theme').addEventListener('click', () => setTheme(effectiveTheme() === 'dark' ? 'light' : 'dark'));
  $('#btn-settings').addEventListener('click', () => openSheet(true));
  $('#btn-sheet-close').addEventListener('click', () => openSheet(false));
  $('#scrim').addEventListener('click', () => openSheet(false));
  addEventListener('keydown', (e) => { if (e.key === 'Escape') openSheet(false); });
  $$('#theme-seg button').forEach((b) => b.addEventListener('click', () => setTheme(b.dataset.themeSet)));

  $('#btn-mom-table').addEventListener('click', (e) => {
    const on = $('#momentum-table').classList.toggle('hidden') === false;
    $('#momentum').classList.toggle('hidden', on);
    e.currentTarget.textContent = on ? '막대로 보기' : '표로 보기';
    e.currentTarget.setAttribute('aria-pressed', String(on));
  });

  ['#rb-cash', '#rb-deposit'].forEach((id) => $(id).addEventListener('input', () => { S.rb.edited = {}; recalc(); }));
  $('#rb-fractional').addEventListener('change', () => { S.rb.edited = {}; recalc(); });
  $('#rb-all').addEventListener('change', renderRebalance);
  $('#orders').addEventListener('input', onOrderInput);
  $('#rb-save').addEventListener('click', (e) => saveRecord(e.currentTarget));

  $$('#rec-tabs button').forEach((b) => b.addEventListener('click', () => { S.recSub = b.dataset.sub; history.replaceState(null, '', `#records/${S.recSub}`); renderRecordsView(); }));
  $('#timeline').addEventListener('change', async (e) => {
    const id = e.target.dataset.memo;
    if (!id) return;
    try { await api(`/api/records/${id}`, { method: 'PATCH', body: JSON.stringify({ memo: e.target.value }) }); toast('메모를 저장했습니다.'); }
    catch (err) { toast(err.message, 'err'); }
  });
  $('#timeline').addEventListener('click', async (e) => {
    const btn = e.target.closest('[data-del]');
    if (!btn) return;
    const r = S.records.find((x) => String(x.id) === btn.dataset.del);
    if (!(await confirmDialog({ title: '기록을 삭제할까요?', body: `${r.rebalance_date} · 총자산 ${usd(r.total_value)}\n삭제하면 되돌릴 수 없습니다.`, okText: '삭제', danger: true }))) return;
    await busy(btn, async () => {
      try { const res = await api(`/api/records/${r.id}`, { method: 'DELETE' }); toast(res.message); await loadRecords(); prefillRebalance(); renderRebalance(); }
      catch (err) { toast(err.message, 'err'); }
    });
  });

  $('#btn-tg-test').addEventListener('click', (e) => busy(e.currentTarget, async () => {
    try { toast((await api('/api/telegram/test', { method: 'POST' })).message); } catch (err) { toast(err.message, 'err'); }
  }));
  $('#btn-tg-signal').addEventListener('click', async (e) => {
    const btn = e.currentTarget;
    if (!(await confirmDialog({ title: '신호를 지금 보낼까요?', body: '이번 달 확정 신호를 텔레그램으로 보냅니다.', okText: '보내기' }))) return;
    busy(btn, async () => {
      try { toast((await api('/api/telegram/signal', { method: 'POST' })).message); loadSystem(); } catch (err) { toast(err.message, 'err'); }
    });
  });
}

(async function init() {
  $('#rb-date').value = todayStr();
  syncThemeSeg();
  bindEvents();
  setView(location.hash.slice(1) || 'signal', false);
  try { await loadRecords(); } catch (err) { toast(`기록 불러오기 실패: ${err.message}`, 'err'); }
  prefillRebalance();
  try { await loadSignal(); }
  catch (err) {
    $('#hero').innerHTML = `<div class="empty"><svg><use href="#i-alert"/></svg><b>신호를 계산하지 못했습니다</b>${esc(err.message)}</div>`;
    toast(err.message, 'err');
  }
})();
