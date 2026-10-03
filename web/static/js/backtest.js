/* 백테스트 화면 — app.js 의 공용 헬퍼($, $$, api, pct, esc, tri, toast, busy, cssVar, crosshair,
 * showTip, hideTip, tcolor, MODE, S)를 사용한다.
 *
 * 동작 (일반 백테스트 프로그램처럼):
 *  - 기본 조건 결과는 서버가 미리 계산 → 앱 로드 직후 받아 두고 탭을 열면 바로 표시
 *  - 조건을 바꾸면 "조건이 변경되었습니다" 표시만, [백테스트 실행]을 눌러야 재계산
 *  - [기본값으로] 는 미리 계산된 기본 결과로 즉시 복귀
 */
'use strict';

const BT = { def: null, result: null, form: null, applied: null, recLimit: 24, loading: null };
const BT_BENCH_ORDER = ['spy', 'qqq', '6040', 'allweather', 'permanent', 'ew8'];   // 색 슬롯 2~7 고정

const btColorVar = (key) => {
  const i = BT_BENCH_ORDER.indexOf(key);
  return i < 0 ? '--s-1' : `--s-${i + 2}`;
};
const num2 = (x) => (x == null ? '-' : x.toFixed(2));
const shiftMonth = (ym, delta) => {
  const [y, m] = ym.split('-').map(Number);
  const t = y * 12 + (m - 1) + delta;
  return `${Math.floor(t / 12)}-${String((t % 12) + 1).padStart(2, '0')}`;
};

/* ── 조건(폼) ─────────────────────────────────────────────────────────────── */
function btFormFromParams(p) {
  return {
    strategy: p.strategy, start: p.start || null, end: p.end || null,
    slippage: p.slippage_pct, cash: p.cash, currency: p.currency, bench: [...p.bench],
    preset: p.start || p.end ? 'custom' : 'all',
  };
}
const btKey = (f) => JSON.stringify([f.strategy, f.start || null, f.end || null, Number(f.slippage), f.cash, f.currency, [...f.bench].sort()]);
function btQuery(f) {
  const q = new URLSearchParams({ strategy: f.strategy, slippage: String(f.slippage), cash: f.cash, currency: f.currency, bench: f.bench.join(',') });
  if (f.start) q.set('start', f.start);
  if (f.end) q.set('end', f.end);
  return q.toString();
}

function btRenderForm() {
  const f = BT.form, meta = BT.result.meta;
  $$('#bt-presets .chip-btn').forEach((b) => b.classList.toggle('on', b.dataset.preset === f.preset));
  const s = $('#bt-start'), e = $('#bt-end');
  s.min = e.min = meta.min_month; s.max = e.max = meta.max_month;
  s.value = f.start || meta.min_month;
  e.value = f.end || meta.max_month;
  $('#bt-slippage').value = f.slippage;
  $$('#bt-cash button').forEach((b) => b.classList.toggle('on', b.dataset.v === f.cash));
  $$('#bt-currency button').forEach((b) => b.classList.toggle('on', b.dataset.v === f.currency));
  $('#bt-bench').innerHTML = meta.benchmarks.map((b) => `
    <button class="chip-btn ${f.bench.includes(b.key) ? 'on' : ''}" data-key="${b.key}" title="${esc(b.desc)}">
      <span class="sw" style="background:var(${btColorVar(b.key)})"></span>${esc(b.name)} <small>${esc(b.desc)}</small></button>`).join('');
  btSyncDirty();
}

function btSyncDirty() {
  const dirty = BT.applied && btKey(BT.form) !== btKey(BT.applied);
  $('#bt-dirty').classList.toggle('hidden', !dirty);
  $('#bt-run').classList.toggle('attn', !!dirty);
}

/* ── 데이터 ───────────────────────────────────────────────────────────────── */
function btLoadDefault() {
  if (BT.def) return Promise.resolve(BT.def);
  if (BT.loading) return BT.loading;
  BT.loading = api('/api/backtest').then((r) => {
    BT.def = r;
    if (!BT.result) {
      BT.result = r;
      BT.form = btFormFromParams(r.params);
      BT.applied = { ...BT.form, bench: [...BT.form.bench] };
    }
    if (S.view === 'backtest') btRender();
    return r;
  }).finally(() => { BT.loading = null; });
  return BT.loading;
}

async function btRun(btn) {
  const f = BT.form;
  if (!(f.slippage >= 0 && f.slippage <= 2)) { toast('슬리피지는 0% ~ 2% 사이로 입력하세요.', 'err'); return; }
  if (f.start && f.end && f.start > f.end) { toast('시작 월이 종료 월보다 늦습니다.', 'err'); return; }
  const layout = $('#bt-layout');
  await busy(btn, async () => {
    layout.classList.add('running');
    const t0 = performance.now();
    try {
      const r = await api(`/api/backtest?${btQuery(f)}`);
      BT.result = r;
      BT.applied = { ...f, bench: [...f.bench] };
      btRender();
      toast(`백테스트 완료 · ${((performance.now() - t0) / 1000).toFixed(1)}초`);
    } catch (err) {
      toast(err.message, 'err');
    } finally {
      layout.classList.remove('running');
    }
  });
}

function btReset() {
  if (!BT.def) return;
  BT.result = BT.def;
  BT.form = btFormFromParams(BT.def.params);
  BT.applied = { ...BT.form, bench: [...BT.form.bench] };
  BT.recLimit = 24;
  btRender();
}

/* ── 렌더 ─────────────────────────────────────────────────────────────────── */
function btAllSeries(r) { return [r.strategy, ...r.benchmarks]; }

function btRender() {
  const r = BT.result;
  if (!r) return;
  const p = r.params, meta = r.meta;
  const names = r.benchmarks.map((b) => b.name).join(', ') || '없음';
  $('#bt-applied').textContent =
    `적용: ${r.strategy.name} · ${meta.start} ~ ${meta.end} (${meta.months}개월) · 슬리피지 ${p.slippage_pct}% · ` +
    `${p.cash === 'cash' ? 'BIL→현금' : 'BIL 수익률'} · ${p.currency === 'krw' ? '원화 환산' : 'USD'} · 비교 ${names} · ` +
    `계산 ${r.computed_at.replace('T', ' ').slice(5, 16)}${r.stale ? ' · ⚠ 가격 조회 실패(이전 데이터)' : ''}`;
  btRenderForm();
  btRenderKpis(r);
  btRenderCharts(r);
  btRenderCompare(r);
  btRenderHeat(r);
  btRenderRecs(r);
}

function btRenderKpis(r) {
  const m = r.strategy.metrics;
  const b0 = r.benchmarks[0];
  const tile = (label, value, sub) => `<div class="stat"><div class="stat-label">${label}</div><div class="stat-value tnum">${value}</div><div class="stat-sub">${sub || '&nbsp;'}</div></div>`;
  $('#bt-kpis').innerHTML = [
    tile('CAGR (연평균)', pct(m.cagr), b0 ? `${esc(b0.name)} ${pct(b0.metrics.cagr)}` : ''),
    tile('MDD (최대 낙폭)', pct(m.mdd), m.mdd_peak ? `${m.mdd_peak} → ${m.mdd_trough}` : ''),
    tile('Sharpe', num2(m.sharpe), '무위험수익률 = BIL'),
    tile('Sortino', num2(m.sortino), '하방 변동성 기준'),
    tile('연 변동성', pct(m.volatility, 2, false), '월수익률 표준편차 × √12'),
    tile('총수익률', pct(m.total_return, 1), `${r.meta.months}개월`),
    tile('Calmar', num2(m.calmar), 'CAGR ÷ |MDD|'),
    tile('월 승률', pct(m.win_rate, 1, false), `방어 모드 ${m.defensive_ratio == null ? '-' : pct(m.defensive_ratio, 0, false)}`),
    tile('연 매매 비중', pct(m.annual_traded, 0, false), '사고판 금액 ÷ 총자산'),
    tile('비용 영향', `−${(m.cost_drag * 100).toFixed(2)}%`, '슬리피지로 줄어든 연 수익률'),
  ].join('');
}

// 데이터 범위에 맞춘 깔끔한 눈금 (1·2·2.5·5 × 10^k) — Chart.js 기본값은 눈금 수 제한 때문에
// 축이 −200% 처럼 데이터보다 훨씬 넓어지는 경우가 있었다
function niceAxis(values, dd) {
  const lo = Math.min(0, ...values), hi = dd ? 0 : Math.max(0, ...values);
  const raw = (hi - lo) / 5 || 0.01;
  const mag = Math.pow(10, Math.floor(Math.log10(raw)));
  const step = [1, 2, 2.5, 5, 10].map((k) => k * mag).find((v) => v >= raw);
  // 음수 쪽이 눈금 한 칸의 절반도 안 되면 데이터 바로 아래까지만 (끝 눈금 라벨은 숨김)
  const min = lo > -step / 2 ? lo - step * 0.08 : Math.floor(lo / step) * step;
  return { min, max: dd ? 0 : Math.ceil(hi / step) * step, ticks: { stepSize: step } };
}

function btLineChart(key, canvas, labels, series, { log = false, dd = false }) {
  if (typeof Chart === 'undefined') return;
  S.charts[key]?.destroy();
  const line = cssVar('--line'), muted = cssVar('--muted'), surface = cssVar('--surface'), ink = cssVar('--ink');
  const val = (s) => (dd ? s.drawdown : log ? s.equity : s.equity.map((v) => v - 1));
  const fmtV = (v) => (log ? pct(v - 1, 1) : pct(v, 1));
  S.charts[key] = new Chart(canvas, {
    type: 'line',
    data: {
      labels,
      datasets: series.map((s) => {
        const color = cssVar(btColorVar(s.key));
        const main = s.kind === 'strategy';
        return {
          label: s.name, data: val(s), borderColor: color, backgroundColor: `${color}1f`,
          borderWidth: main ? 2.6 : 1.6, fill: main && !log ? 'origin' : false, order: main ? 0 : 1,
          pointRadius: 0, pointHoverRadius: 4, pointBackgroundColor: color, pointBorderColor: surface, pointBorderWidth: 2,
          borderCapStyle: 'round', borderJoinStyle: 'round', tension: 0,
        };
      }),
    },
    options: {
      responsive: true, maintainAspectRatio: false, animation: { duration: 250 },
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: surface, titleColor: ink, bodyColor: ink, borderColor: line, borderWidth: 1,
          padding: 10, cornerRadius: 10, usePointStyle: true, boxWidth: 8, boxHeight: 8,
          itemSort: (a, b) => b.parsed.y - a.parsed.y,
          callbacks: { label: (c) => ` ${c.dataset.label}  ${fmtV(c.parsed.y)}` },
        },
      },
      scales: {
        x: { grid: { display: false }, border: { color: line }, ticks: { color: muted, maxRotation: 0, autoSkipPadding: 24, font: { size: 11 } } },
        y: {
          type: log ? 'logarithmic' : 'linear',
          grid: { color: line }, border: { display: false },
          ...(log ? {} : niceAxis(series.flatMap(val), dd)),
          ticks: { color: muted, font: { size: 11 }, ...(log ? { maxTicksLimit: 6 } : { stepSize: niceAxis(series.flatMap(val), dd).ticks.stepSize }), callback: (v) => {
            if (log) return pct(v - 1, 0);
            const st = niceAxis(series.flatMap(val), dd).ticks.stepSize;
            return Math.abs(v / st - Math.round(v / st)) > 1e-6 ? '' : pct(v, 0);   // 정렬 안 된 끝 눈금은 라벨 생략
          } },
        },
      },
    },
    plugins: [crosshair],
  });
}

function btRenderCharts(r) {
  const series = btAllSeries(r);
  const log = $('#bt-log').checked;
  $('#bt-chart-sub').textContent = `${r.meta.start} ~ ${r.meta.end} · ${r.params.currency === 'krw' ? '원화 환산' : 'USD'} · 비용 차감 후`;
  $('#bt-legend').innerHTML = series.map((s) => `<span><i style="background:var(${btColorVar(s.key)})${s.kind === 'strategy' ? ';height:4px' : ''}"></i>${esc(s.name)} <b>${pct(s.metrics.total_return, 0)}</b> <span class="muted">CAGR ${pct(s.metrics.cagr, 1)}</span></span>`).join('');
  btLineChart('bt', $('#bt-chart'), r.labels, series, { log });
  btLineChart('btdd', $('#bt-dd'), r.labels, series, { dd: true });
}

const BT_ROWS = [
  ['CAGR', (m) => m.cagr, (v) => pct(v), 1],
  ['총수익률', (m) => m.total_return, (v) => pct(v, 1), 1],
  ['MDD', (m) => m.mdd, (v) => pct(v), 1],
  ['연 변동성', (m) => m.volatility, (v) => pct(v, 2, false), -1],
  ['Sharpe', (m) => m.sharpe, num2, 1],
  ['Sortino', (m) => m.sortino, num2, 1],
  ['Calmar', (m) => m.calmar, num2, 1],
  ['월 승률', (m) => m.win_rate, (v) => pct(v, 1, false), 1],
  ['최고 월', (m) => m.best_month, (v) => `${pct(v.ret, 1)}<small>${v.month}</small>`, 0],
  ['최저 월', (m) => m.worst_month, (v) => `${pct(v.ret, 1)}<small>${v.month}</small>`, 0],
  ['MDD 구간', (m) => m, (m) => (m.mdd_peak ? `${m.mdd_peak}<small>→ ${m.mdd_trough} · 회복 ${m.mdd_recovery || '미회복'}</small>` : '-'), 0],
  ['연 매매 비중', (m) => m.annual_traded, (v) => pct(v, 0, false), -1],
  ['비용 영향 (연)', (m) => m.cost_drag, (v) => `−${(v * 100).toFixed(2)}%`, -1],
];

function btRenderCompare(r) {
  const series = btAllSeries(r);
  const head = `<tr><th>지표</th>${series.map((s) => `<th><span class="sw" style="background:var(${btColorVar(s.key)})"></span>${esc(s.name)}</th>`).join('')}</tr>`;
  const rows = BT_ROWS.map(([label, get, fmt, dir]) => {
    const vals = series.map((s) => get(s.metrics));
    let best = -1;
    if (dir && series.length > 1) {
      const nums = vals.map((v) => (v == null ? null : v * dir));
      const mx = Math.max(...nums.filter((v) => v != null));
      best = nums.indexOf(mx);
    }
    return `<tr><td>${label}</td>${vals.map((v, i) => `<td class="${i === best ? 'best' : ''}">${v == null ? '-' : fmt(v)}</td>`).join('')}</tr>`;
  }).join('');
  $('#bt-compare').innerHTML = `<table class="tbl compare"><thead>${head}</thead><tbody>${rows}</tbody></table>`;
}

/* 히트맵 색: 다이버징 (하락 파랑 ↔ 0 회색 ↔ 상승 빨강), 대칭 도메인 */
function hexRgb(h) { const n = parseInt(h.replace('#', ''), 16); return [(n >> 16) & 255, (n >> 8) & 255, n & 255]; }
function heatStyle(v, dom) {
  if (v == null) return '';
  const t = Math.max(-1, Math.min(1, v / dom));
  const mid = hexRgb(cssVar('--heat-mid')), end = hexRgb(cssVar(t >= 0 ? '--heat-pos' : '--heat-neg'));
  const k = Math.pow(Math.abs(t), 0.85);
  const c = mid.map((m, i) => Math.round(m + (end[i] - m) * k));
  const lum = (0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]) / 255;
  return `background:rgb(${c.join(',')});color:${lum < 0.55 ? '#fff' : '#111827'}`;
}

function btRenderHeat(r) {
  const hm = [...r.strategy.heatmap].reverse();
  const MON = 0.06, YEAR = 0.3;
  const head = `<tr><th></th>${[...Array(12)].map((_, i) => `<th>${i + 1}월</th>`).join('')}<th>연간</th></tr>`;
  const rows = hm.map((y) => `<tr><th class="y">${y.year}</th>${y.months.map((v, i) =>
    v == null ? '<td class="na">·</td>' : `<td style="${heatStyle(v, MON)}" data-y="${y.year}" data-m="${i + 1}" data-v="${v}">${(v * 100).toFixed(1)}</td>`).join('')}
    <td class="annual" style="${heatStyle(y.annual, YEAR)}" data-y="${y.year}" data-v="${y.annual}" data-annual="${y.partial ? 'partial' : 'full'}">${(y.annual * 100).toFixed(1)}</td></tr>`).join('');
  $('#bt-heat').innerHTML = `<table class="heat"><thead>${head}</thead><tbody>${rows}</tbody></table>
    <div class="heat-scale"><span>${pct(-MON, 0)}</span><i></i><span>${pct(MON, 0)}</span><span>· 단위 % · 연간 열은 ±${YEAR * 100}% 기준 색</span></div>`;
  $('#bt-heat-sub').textContent = `${r.strategy.name} · 비용 차감 후 · ${r.params.currency === 'krw' ? '원화 환산' : 'USD'}`;
}

function btRenderRecs(r) {
  const recs = r.strategy.records;
  const cashMode = r.params.cash === 'cash';
  const rows = recs.slice(0, BT.recLimit).map((x) => `<tr>
    <td><b>${x.month}</b></td>
    <td>${x.mode ? `<span class="mode-tag ${x.mode}">${MODE[x.mode].title}</span>` : '-'}</td>
    <td class="wrap" style="text-align:left">${Object.entries(x.weights).map(([t, w]) => `<span class="chip" style="padding:2px 8px;font-size:12px;margin:1px"><span class="sw" style="background:${tcolor(t)}"></span>${t}${cashMode && t === 'BIL' ? '→현금' : ''}${w !== 0.25 ? ` ${pct(w, 0, false)}` : ''}</span>`).join('')}</td>
    <td>${pct(x.traded, 0, false)}</td>
    <td>${(x.cost * 100).toFixed(2)}%</td>
    <td><b>${tri(x.ret)} ${pct(x.ret)}</b></td></tr>`).join('');
  $('#bt-recs').innerHTML = `<table class="tbl"><thead><tr><th>적용 월</th><th>모드</th><th style="text-align:left">편입 종목</th><th>매매 비중</th><th>비용</th><th>월 수익률</th></tr></thead><tbody>${rows}</tbody></table>`;
  const more = $('#bt-more');
  more.classList.toggle('hidden', BT.recLimit >= recs.length);
  more.textContent = `더 보기 (${Math.min(BT.recLimit, recs.length)} / ${recs.length})`;
}

/* ── 이벤트 ───────────────────────────────────────────────────────────────── */
function btBind() {
  $('#bt-presets').addEventListener('click', (e) => {
    const b = e.target.closest('[data-preset]');
    if (!b || !BT.form) return;
    const meta = BT.result.meta;
    const pr = b.dataset.preset;
    BT.form.preset = pr;
    if (pr === 'all') { BT.form.start = null; BT.form.end = null; }
    else {
      BT.form.end = null;
      const s = shiftMonth(meta.max_month, -(Number(pr) * 12 - 1));
      BT.form.start = s < meta.min_month ? null : s;
    }
    btRenderForm();
  });
  ['#bt-start', '#bt-end'].forEach((id) => $(id).addEventListener('change', (e) => {
    if (!BT.form) return;
    const meta = BT.result.meta;
    let v = e.target.value || null;
    if (id === '#bt-start' && v === meta.min_month) v = null;
    if (id === '#bt-end' && v === meta.max_month) v = null;
    BT.form[id === '#bt-start' ? 'start' : 'end'] = v;
    BT.form.preset = BT.form.start || BT.form.end ? 'custom' : 'all';
    btRenderForm();
  }));
  $('#bt-slippage').addEventListener('input', (e) => { if (BT.form) { BT.form.slippage = parseFloat(e.target.value); btSyncDirty(); } });
  $('#bt-cash').addEventListener('click', (e) => { const b = e.target.closest('[data-v]'); if (b && BT.form) { BT.form.cash = b.dataset.v; btRenderForm(); } });
  $('#bt-currency').addEventListener('click', (e) => { const b = e.target.closest('[data-v]'); if (b && BT.form) { BT.form.currency = b.dataset.v; btRenderForm(); } });
  $('#bt-bench').addEventListener('click', (e) => {
    const b = e.target.closest('[data-key]');
    if (!b || !BT.form) return;
    const k = b.dataset.key;
    BT.form.bench = BT.form.bench.includes(k) ? BT.form.bench.filter((x) => x !== k) : [...BT.form.bench, k];
    btRenderForm();
  });
  $('#bt-run').addEventListener('click', (e) => { if (BT.form) btRun(e.currentTarget); });
  $('#bt-reset').addEventListener('click', btReset);
  $('#bt-log').addEventListener('change', () => { if (BT.result) btRenderCharts(BT.result); });
  $('#bt-more').addEventListener('click', () => { BT.recLimit += 48; btRenderRecs(BT.result); });

  const heat = $('#bt-heat');
  heat.addEventListener('pointermove', (e) => {
    const td = e.target.closest('td[data-v]');
    if (!td) { hideTip(); return; }
    const v = Number(td.dataset.v);
    const title = td.dataset.m ? `${td.dataset.y}년 ${td.dataset.m}월` : `${td.dataset.y}년 ${td.dataset.annual === 'partial' ? '(일부 기간)' : '연간'}`;
    showTip(`<div class="tip-title">${title}</div><div class="tip-row"><span>${BT.result.strategy.name} 수익률</span><b>${pct(v)}</b></div>`, e.clientX, e.clientY);
  });
  heat.addEventListener('pointerleave', hideTip);
}

window.renderBacktestView = async function renderBacktestView() {
  if (BT.result) { btRender(); return; }
  $('#bt-kpis').innerHTML = '<div class="stat skeleton" style="height:96px"></div>'.repeat(5);
  $('#bt-applied').textContent = '기본 백테스트 결과를 불러오는 중…';
  try { await btLoadDefault(); }
  catch (err) {
    $('#bt-kpis').innerHTML = `<div class="stat"><div class="stat-label">백테스트를 불러오지 못했습니다</div><div class="stat-sub">${esc(err.message)}</div></div>`;
    toast(err.message, 'err');
  }
};

btBind();
if (S.view === 'backtest') window.renderBacktestView();
else setTimeout(() => btLoadDefault().catch(() => {}), 1200);   // 신호 화면 로딩을 먼저 하고 미리 받아 둠
