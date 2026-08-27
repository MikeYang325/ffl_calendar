const $ = (id) => document.getElementById(id);
let META = null;
let tripMode = 'oneway';
let overviewQueryTimer = null;
let overviewAbortController = null;
const AIRPORT_PICKERS = {};

const esc = (s) => String(s ?? '').replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));

const AIRPORT_TAB_GROUPS = [
  { key: 'hot', label: '🔥 热门', letters: [] },
  { key: 'ABCDEF', label: 'ABCDEF', letters: ['A','B','C','D','E','F'] },
  { key: 'GHIJ', label: 'GHIJ', letters: ['G','H','I','J'] },
  { key: 'KLMN', label: 'KLMN', letters: ['K','L','M','N'] },
  { key: 'PQRSTUV', label: 'PQRSTUV', letters: ['P','Q','R','S','T','U','V'] },
  { key: 'WXYZ', label: 'WXYZ', letters: ['W','X','Y','Z'] },
];

const HOT_AIRPORT_CODES = [
  'PEK','PKX','SHA','PVG','CAN','SZX','TFU','CTU',
  'CKG','XIY','KMG','HGH','NKG','WUH','TSN','TAO',
  'XMN','SYX','DLC','HRB','CSX','CGO','TNA','FOC',
  'KWE','NNG','HAK','LXA','URC','LHW','XNN','INC',
  'HET','TYN','SJW'
];

function optionHtml(items, placeholder='请选择') {
  return `<option value="">${placeholder}</option>` + items.map(x => `<option value="${esc(x.code)}">${esc(x.label)}</option>`).join('');
}

function airportInfo(code) {
  return META?.airports?.find(x => x.code === code) || null;
}

function airportLabel(code) {
  const item = airportInfo(code);
  if (item) return `${item.name} ${item.code}`;
  const city = META?.cities?.find(x => x.name === code);
  return city ? `${city.name} ${city.codes.join('/')}` : '';
}

function airportMatches(item, keyword) {
  if (!keyword) return true;
  const q = keyword.trim().toUpperCase().replace(/\s+/g, '');
  if (!q) return true;
  return (item._searchKey || '').includes(q);
}

function refreshAirportPicker(selectId) {
  const picker = AIRPORT_PICKERS[selectId];
  if (!picker) return;
  picker.input.value = airportLabel(picker.select.value);
}

function refreshAllAirportPickers() {
  Object.keys(AIRPORT_PICKERS).forEach(refreshAirportPicker);
}

function enhanceAirportSelect(selectId, placeholder, allowCities=false) {
  const select = $(selectId);
  if (!select || AIRPORT_PICKERS[selectId]) return;

  select.classList.add('select-hidden');

  const picker = document.createElement('div');
  picker.className = 'airport-picker';
  picker.innerHTML = `
    <input class="airport-input" type="text" autocomplete="off"
           placeholder="${esc(placeholder)}" aria-haspopup="dialog" aria-expanded="false" />
    <div class="airport-dropdown" hidden>
      <div class="airport-modal-head">
        <strong>选择城市 / 机场</strong>
        <button type="button" class="airport-close" aria-label="关闭">×</button>
      </div>
      <div class="airport-search-wrap">
        <span class="airport-search-icon">⌕</span>
        <input class="airport-search" type="text" autocomplete="off"
               placeholder="输入城市、机场或三字码" />
        <button type="button" class="airport-search-clear" hidden aria-label="清空">×</button>
      </div>
      <div class="airport-tabs" role="tablist"></div>
      <div class="airport-content">
        <div class="airport-result-title"></div>
        <div class="airport-grid"></div>
      </div>
    </div>`;
  select.insertAdjacentElement('afterend', picker);

  const input = picker.querySelector('.airport-input');
  const dropdown = picker.querySelector('.airport-dropdown');
  const search = picker.querySelector('.airport-search');
  const clearBtn = picker.querySelector('.airport-search-clear');
  const closeBtn = picker.querySelector('.airport-close');
  const tabs = picker.querySelector('.airport-tabs');
  const grid = picker.querySelector('.airport-grid');
  const resultTitle = picker.querySelector('.airport-result-title');

  const state = {
    picker, select, input, dropdown, search, clearBtn, closeBtn,
    tabs, grid, resultTitle, activeTab: 'hot',
    hotItems: null, lastRenderKey: null, renderedTabsFor: null, prewarmed: false,
  };
  AIRPORT_PICKERS[selectId] = state;

  function hotAirports() {
    if (state.hotItems) return state.hotItems;
    const byCode = new Map((META.airports || []).map(x => [x.code, x]));
    const hot = HOT_AIRPORT_CODES.map(c => byCode.get(c)).filter(Boolean);
    if (hot.length < 12) {
      const seen = new Set(hot.map(x => x.code));
      for (const item of (META.airports || [])) {
        if (!seen.has(item.code)) {
          hot.push(item);
          seen.add(item.code);
        }
        if (hot.length >= 30) break;
      }
    }
    state.hotItems = hot;
    return state.hotItems;
  }

  function tabAirports(key) {
    if (key === 'hot') return hotAirports();
    const tab = AIRPORT_TAB_GROUPS.find(x => x.key === key);
    if (!tab) return [];
    return (META.airports || []).filter(x => tab.letters.includes(x.initial));
  }

  function renderTabs() {
    if (state.renderedTabsFor === state.activeTab && tabs.childElementCount) return;
    tabs.innerHTML = AIRPORT_TAB_GROUPS.map(tab => `
      <button type="button" role="tab"
              class="airport-tab ${state.activeTab === tab.key ? 'active' : ''}"
              data-tab="${esc(tab.key)}">${esc(tab.label)}</button>
    `).join('');
    state.renderedTabsFor = state.activeTab;
  }

  function renderGrid(items, title='', grouped=false) {
    if (!items.length) {
      resultTitle.textContent = '';
      grid.innerHTML = '<div class="airport-empty">没有匹配的城市或机场</div>';
      grid.classList.remove('grouped');
      return;
    }

    resultTitle.textContent = title;
    grid.classList.toggle('grouped', grouped);

    if (!grouped) {
      grid.innerHTML = items.map(item => `
        <button type="button" class="airport-city" data-value="${esc(item.value || item.code)}">
          <span class="airport-city-name">${esc(item.name)}</span>
          <span class="airport-city-code">${esc(item.code)}</span>
        </button>`).join('');
      return;
    }

    const groups = new Map();
    items.forEach(item => {
      const letter = /^[A-Z]$/.test(item.initial || '') ? item.initial : '#';
      if (!groups.has(letter)) groups.set(letter, []);
      groups.get(letter).push(item);
    });

    grid.innerHTML = [...groups.entries()].map(([letter, groupItems]) => `
      <div class="airport-letter-row">${esc(letter)}</div>
      ${groupItems.map(item => `
        <button type="button" class="airport-city" data-value="${esc(item.value || item.code)}">
          <span class="airport-city-name">${esc(item.name)}</span>
          <span class="airport-city-code">${esc(item.code)}</span>
        </button>`).join('')}
    `).join('');
  }

  function render() {
    const keyword = search.value.trim();
    const renderKey = `${state.activeTab}\u0000${keyword}`;
    clearBtn.hidden = !keyword;
    if (state.lastRenderKey === renderKey) return;
    state.lastRenderKey = renderKey;

    if (keyword) {
      const matchedAirports = (META.airports || []).filter(item => airportMatches(item, keyword));
      const normalized = keyword.trim().toUpperCase().replace(/\s+/g, '');
      const matchedCities = allowCities ? (META.cities || [])
        .filter(city => (city._searchKey || '').includes(normalized))
        .map(city => ({
          name: city.name,
          code: (city.codes || []).join('/'),
          value: city.name,
          label: city.label,
          aggregate: true,
        })) : [];
      const matched = [...matchedCities, ...matchedAirports];
      renderTabs();
      renderGrid(matched, `搜索结果 · ${matched.length}`, false);
      return;
    }

    renderTabs();
    const items = tabAirports(state.activeTab);
    renderGrid(items, state.activeTab === 'hot' ? '热门城市' : '', state.activeTab !== 'hot');
  }

  function close() {
    picker.classList.remove('open', 'align-right');
    dropdown.hidden = true;
    input.setAttribute('aria-expanded', 'false');
    search.value = '';
    clearBtn.hidden = true;
  }

  function closeOthers() {
    Object.entries(AIRPORT_PICKERS).forEach(([id, p]) => {
      if (id !== selectId && !p.dropdown.hidden) {
        p.picker.classList.remove('open', 'align-right');
        p.dropdown.hidden = true;
        p.input.setAttribute('aria-expanded', 'false');
        p.search.value = '';
      }
    });
  }

  function open(prefill='') {
    closeOthers();
    picker.classList.add('open');
    dropdown.hidden = false;
    input.setAttribute('aria-expanded', 'true');
    search.value = prefill;
    render();

    requestAnimationFrame(() => {
      picker.classList.remove('align-right');
      const r = dropdown.getBoundingClientRect();
      if (r.right > window.innerWidth - 8) picker.classList.add('align-right');
    });

    setTimeout(() => search.focus(), 0);
  }

  function choose(code) {
    select.value = code;
    refreshAirportPicker(selectId);
    select.dispatchEvent(new Event('change', { bubbles: true }));
    close();
  }

  input.addEventListener('focus', () => open(''));
  input.addEventListener('click', () => {
    if (dropdown.hidden) open('');
  });
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') close();
    if (e.key === 'Enter' && dropdown.hidden) {
      e.preventDefault();
      open('');
    }
  });

  search.addEventListener('input', render);
  search.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') close();
    if (e.key === 'Enter') {
      e.preventDefault();
      const first = grid.querySelector('.airport-city');
      if (first) choose(first.dataset.value);
    }
  });

  clearBtn.addEventListener('click', (e) => {
    e.preventDefault();
    e.stopPropagation();
    search.value = '';
    render();
    search.focus();
  });

  closeBtn.addEventListener('click', close);

  tabs.addEventListener('click', (e) => {
    const btn = e.target.closest('[data-tab]');
    if (!btn) return;

    // render() 会重建标签 DOM。
    // 如果不阻止冒泡，事件继续到 document 时，
    // 原点击按钮已经被移除，会被误判为“点击弹层外部”，从而关闭面板。
    e.preventDefault();
    e.stopPropagation();

    state.activeTab = btn.dataset.tab;
    search.value = '';
    render();
  });

  grid.addEventListener('click', (e) => {
    const btn = e.target.closest('.airport-city');
    if (btn) choose(btn.dataset.value);
  });

  select.addEventListener('change', () => refreshAirportPicker(selectId));

  document.addEventListener('click', (e) => {
    if (!picker.contains(e.target) && e.target !== select) close();
  });

  window.addEventListener('resize', () => {
    if (!dropdown.hidden) {
      picker.classList.remove('align-right');
      const r = dropdown.getBoundingClientRect();
      if (r.right > window.innerWidth - 8) picker.classList.add('align-right');
    }
  });

  state.prewarm = () => {
    if (state.prewarmed) return;
    render();
    state.prewarmed = true;
  };
}

function prewarmAirportPickers() {
  const run = () => Object.values(AIRPORT_PICKERS).forEach(picker => picker.prewarm?.());
  if ('requestIdleCallback' in window) {
    window.requestIdleCallback(run, { timeout: 200 });
  } else {
    setTimeout(run, 16);
  }
}

function setDefaultAirports() {
  const origin = $('originSelect');
  const dest = $('destinationSelect');
  if ([...origin.options].some(o => o.value === 'PEK')) origin.value = 'PEK';
  if ([...dest.options].some(o => o.value === 'CAN')) dest.value = 'CAN';
  const overview = $('overviewOriginSelect');
  const hasBeijing = (META.cities || []).some(x => x.name === '北京');
  overview.value = hasBeijing && [...overview.options].some(o => o.value === '北京')
    ? '北京'
    : (origin.value || 'PEK');
  refreshAllAirportPickers();
}

async function init() {
  const res = await fetch('/api/meta');
  META = await res.json();
  (META.airports || []).forEach(item => {
    item._searchKey = [item.name, item.code, item.label, item.initial, item.search]
      .filter(Boolean)
      .map(v => String(v).toUpperCase().replace(/\s+/g, ''))
      .join('|');
  });
  (META.cities || []).forEach(city => {
    city._searchKey = [city.name, city.label, ...(city.codes || [])]
      .filter(Boolean)
      .map(v => String(v).toUpperCase().replace(/\s+/g, ''))
      .join('|');
  });
  $('dataBadge').textContent = `数据 ${META.date_min} → ${META.date_max}`;
  $('originSelect').innerHTML = optionHtml(META.airports, '选择出发机场');
  $('destinationSelect').innerHTML = optionHtml(META.airports, '选择到达机场');
  $('overviewOriginSelect').innerHTML = optionHtml(META.airports, '选择出发城市 / 机场')
    + (META.cities || []).map(x => `<option value="${esc(x.name)}">${esc(x.label)}</option>`).join('');
  enhanceAirportSelect('originSelect', '输入出发城市 / 机场 / 三字码');
  enhanceAirportSelect('destinationSelect', '输入到达城市 / 机场 / 三字码');
  enhanceAirportSelect('overviewOriginSelect', '输入出发城市 / 机场 / 三字码', true);
  $('airlineSelect').innerHTML = `<option value="">全部航司</option>` + META.airlines.map(x => `<option value="${x.code}">${x.label}</option>`).join('');
  $('overviewAirline').innerHTML = $('airlineSelect').innerHTML;
  $('membershipSelect').value = '666';
  $('overviewMembership').value = '666';
  $('departureDate').min = META.date_min;
  $('departureDate').max = META.date_max;
  $('returnDate').min = META.date_min;
  $('returnDate').max = META.date_max;
  $('departureDate').value = META.date_min;
  const plus7 = new Date(`${META.date_min}T00:00:00`); plus7.setDate(plus7.getDate()+7);
  $('returnDate').value = plus7.toISOString().slice(0,10) <= META.date_max ? plus7.toISOString().slice(0,10) : META.date_max;
  setDefaultAirports();
  prewarmAirportPickers();
  renderStats();
  loadOverview();
}

function renderStats() {
  $('statsGrid').innerHTML = `
    <div class="stat"><span>航班记录</span><strong>${META.flight_records.toLocaleString()}</strong></div>
    <div class="stat"><span>直飞航线</span><strong>${META.route_count.toLocaleString()}</strong></div>
    <div class="stat"><span>覆盖机场</span><strong>${META.airport_count.toLocaleString()}</strong></div>`;
}

function flightCard(itin) {
  const segs = itin.segments;
  const head = segs.length === 1 ? `${segs[0].airline} ${segs[0].flight_no}` : `${segs[0].origin_name} → ${segs.at(-1).destination_name}`;
  const segmentsHtml = segs.map((s, idx) => {
    const cross = s.cross_day > 0 ? ` +${s.cross_day}` : '';
    const conn = idx < segs.length - 1 ? (() => {
      const a = new Date(`${s.arrival_date}T${s.arrival_time}:00`);
      const n = segs[idx+1];
      const b = new Date(`${n.departure_date}T${n.departure_time}:00`);
      const mins = Math.round((b-a)/60000);
      return `<div class="connection">在 ${esc(s.destination_name)} ${esc(s.destination)} 中转 ${Math.floor(mins/60)}小时${mins%60 ? (mins%60)+'分' : ''}</div>`;
    })() : '';
    return `
      <div class="segment">
        <div class="time-block"><strong>${esc(s.departure_time)}</strong><span>${esc(s.origin_name)} ${esc(s.origin)}</span><span>${esc(s.departure_date)}</span></div>
        <div class="timeline"><span>${esc(s.duration_text)}</span><span class="plane">✈</span></div>
        <div class="time-block right"><strong>${esc(s.arrival_time)}${cross}</strong><span>${esc(s.destination_name)} ${esc(s.destination)}</span><span>${esc(s.arrival_date)}</span></div>
        <div class="segment-meta">
          <span>${esc(s.airline)} · ${esc(s.flight_no)}</span>
          ${s.aircraft ? `<span>机型 ${esc(s.aircraft)}</span>` : ''}
          <span>产品 ${esc(s.product)}</span>
          ${s.code_share ? '<span>代码共享</span>' : ''}
        </div>
      </div>${conn}`;
  }).join('');
  return `
    <article class="flight-card">
      <div class="flight-card-head">
        <div><strong>${esc(head)}</strong><div class="flight-summary">总行程 ${esc(itin.total_text)}</div></div>
        <div class="tags"><span class="tag ${itin.stops ? 'stop' : ''}">${itin.stops ? itin.stops+'次中转' : '直飞'}</span><span class="tag product">${esc(itin.product)}</span></div>
      </div>
      ${segmentsHtml}
    </article>`;
}

async function doSearch(origin, destination, date) {
  const p = new URLSearchParams({
    origin, destination, date,
    membership: $('membershipSelect').value,
    max_stops: $('maxStopsSelect').value,
    airline: $('airlineSelect').value,
    flight_no: $('flightNoInput').value.trim(),
    sort: $('sortSelect').value,
  });
  const r = await fetch('/api/search?' + p.toString());
  const data = await r.json();
  if (!r.ok) throw new Error(data.error || '查询失败');
  return data;
}

async function searchFlights() {
  const origin = $('originSelect').value;
  const destination = $('destinationSelect').value;
  const date = $('departureDate').value;
  if (!origin || !destination || !date) return alert('请选择出发机场、到达机场和日期');
  if (origin === destination) return alert('出发和到达机场不能相同');

  $('searchBtn').disabled = true;
  $('searchBtn').textContent = '正在搜索…';
  $('results').className = 'results-list empty-state';
  $('results').textContent = '正在计算航线…';
  $('returnResultsWrap').classList.add('hidden');

  try {
    const data = await doSearch(origin, destination, date);
    const originName = META.airports.find(x=>x.code===origin)?.name || origin;
    const destinationName = META.airports.find(x=>x.code===destination)?.name || destination;
    $('resultTitle').textContent = tripMode === 'roundtrip'
      ? `去程 · ${originName} → ${destinationName}`
      : `${originName} → ${destinationName}`;
    $('resultSubtitle').textContent = `${date} · 共 ${data.count} 个方案`;
    $('results').className = 'results-list';
    $('results').innerHTML = data.count ? data.results.map(flightCard).join('') : '<div class="empty-state">没有找到符合条件的航班</div>';

    if (tripMode === 'roundtrip') {
      const returnDate = $('returnDate').value;
      if (!returnDate) throw new Error('请选择返程日期');
      const rd = await doSearch(destination, origin, returnDate);
      $('returnResultsWrap').classList.remove('hidden');
      $('returnTitle').textContent = `返程 · ${destinationName} → ${originName}`;
      $('returnSubtitle').textContent = `${returnDate} · 共 ${rd.count} 个方案`;
      $('returnResults').innerHTML = rd.count ? rd.results.map(flightCard).join('') : '<div class="empty-state">没有找到符合条件的返程航班</div>';
    }
  } catch (e) {
    $('results').className = 'results-list';
    $('results').innerHTML = `<div class="empty-state">${esc(e.message)}</div>`;
  } finally {
    $('searchBtn').disabled = false;
    $('searchBtn').textContent = '搜索航班';
  }
}

function isoDateLocal(year, month, day) {
  return `${year}-${String(month).padStart(2,'0')}-${String(day).padStart(2,'0')}`;
}

function dateRangeList(startText, endText) {
  const out = [];
  const start = new Date(`${startText}T00:00:00`);
  const end = new Date(`${endText}T00:00:00`);
  for (let d = new Date(start); d <= end; d.setDate(d.getDate() + 1)) {
    out.push(`${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`);
  }
  return out;
}

function groupedDateText(dates) {
  const groups = new Map();
  dates.forEach(date => {
    const [y,m,d] = date.split('-');
    const key = `${y}-${m}`;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(String(Number(d)));
  });
  return [...groups.entries()].map(([ym, days]) => {
    const [y,m] = ym.split('-');
    return `<div class="date-list-line"><strong>${Number(m)}月</strong><span>${days.join('、')}</span></div>`;
  }).join('');
}

function routeCalendarHtml(route) {
  const startText = route.data_start || META.date_min;
  const endText = route.data_end || META.date_max;
  const operating = new Set(route.operating_dates || []);
  const dateFlights = route.date_flights || {};
  const weekdayFilter = Number(route.weekday_filter || 0);

  const matchesWeekday = (date) => {
    if (!weekdayFilter) return true;
    const day = new Date(`${date}T00:00:00`).getDay();
    return (day === 0 ? 7 : day) === weekdayFilter;
  };

  const start = new Date(`${startText}T00:00:00`);
  const end = new Date(`${endText}T00:00:00`);
  const months = [];
  let cursor = new Date(start.getFullYear(), start.getMonth(), 1);
  const lastMonth = new Date(end.getFullYear(), end.getMonth(), 1);

  while (cursor <= lastMonth) {
    const year = cursor.getFullYear();
    const month = cursor.getMonth() + 1;
    const daysInMonth = new Date(year, month, 0).getDate();
    const firstDay = new Date(year, month - 1, 1);
    const mondayOffset = (firstDay.getDay() + 6) % 7;
    const cells = [];

    for (let i = 0; i < mondayOffset; i++) {
      cells.push('<span class="calendar-day blank"></span>');
    }

    for (let day = 1; day <= daysInMonth; day++) {
      const date = isoDateLocal(year, month, day);
      const inRange = date >= startText && date <= endText;
      const selectedWeekday = matchesWeekday(date);
      const isOperating = operating.has(date) && selectedWeekday;
      const flights = (dateFlights[date] || []).join(' / ');

      let cls = 'calendar-day';
      let title = '';
      if (!inRange || (weekdayFilter && !selectedWeekday)) {
        cls += ' outside';
      } else if (isOperating) {
        cls += ' route-on';
        title = `${date}：有航线${flights ? `；${flights}` : ''}`;
      } else {
        cls += ' route-off';
        title = `${date}：无航线`;
      }
      cells.push(`<span class="${cls}" title="${esc(title)}">${day}</span>`);
    }

    months.push(`
      <div class="route-calendar-month">
        <div class="calendar-month-title">${year}年${month}月</div>
        <div class="calendar-weekdays">
          <span>一</span><span>二</span><span>三</span><span>四</span><span>五</span><span>六</span><span>日</span>
        </div>
        <div class="calendar-days">${cells.join('')}</div>
      </div>
    `);
    cursor = new Date(year, month, 1);
  }

  return `
    <div class="route-date-panel">
      <div class="route-date-summary simple-route-legend">
        <div><span class="legend-dot route-on"></span><strong>有航线</strong></div>
        <div><span class="legend-dot route-off"></span><strong>无航线</strong></div>
      </div>
      <div class="route-calendars">${months.join('')}</div>
    </div>
  `;
}


let activeMobileCalendarButton = null;

function ensureMobileRouteCalendarSheet() {
  let overlay = document.querySelector('.mobile-route-calendar-overlay');
  if (overlay) return overlay;

  overlay = document.createElement('div');
  overlay.className = 'mobile-route-calendar-overlay';
  overlay.hidden = true;
  overlay.innerHTML = `
    <section class="mobile-route-calendar-sheet" role="dialog" aria-modal="true" aria-label="具体运行日期">
      <div class="mobile-route-calendar-head">
        <div>
          <strong>具体运行日期</strong>
          <span class="mobile-route-calendar-subtitle"></span>
        </div>
        <button type="button" class="mobile-route-calendar-close" aria-label="关闭">×</button>
      </div>
      <div class="mobile-route-calendar-scroll"></div>
    </section>`;
  document.body.appendChild(overlay);

  const close = () => closeMobileRouteCalendarSheet();
  overlay.querySelector('.mobile-route-calendar-close').addEventListener('click', close);
  overlay.addEventListener('click', (event) => {
    if (event.target === overlay) close();
  });
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && !overlay.hidden) close();
  });
  window.addEventListener('resize', () => {
    if (window.innerWidth > 640 && !overlay.hidden) close();
  });
  return overlay;
}

function closeMobileRouteCalendarSheet() {
  const overlay = document.querySelector('.mobile-route-calendar-overlay');
  if (!overlay || overlay.hidden) return;
  overlay.classList.remove('open');
  document.body.classList.remove('mobile-calendar-open');
  if (activeMobileCalendarButton) {
    activeMobileCalendarButton.textContent = '▶';
    activeMobileCalendarButton.setAttribute('aria-expanded', 'false');
    activeMobileCalendarButton = null;
  }
  setTimeout(() => {
    if (!overlay.classList.contains('open')) overlay.hidden = true;
  }, 180);
}

function openMobileRouteCalendarSheet(route, button) {
  const overlay = ensureMobileRouteCalendarSheet();
  if (activeMobileCalendarButton === button && !overlay.hidden) {
    closeMobileRouteCalendarSheet();
    return;
  }

  if (activeMobileCalendarButton && activeMobileCalendarButton !== button) {
    activeMobileCalendarButton.textContent = '▶';
    activeMobileCalendarButton.setAttribute('aria-expanded', 'false');
  }
  activeMobileCalendarButton = button;
  button.textContent = '▼';
  button.setAttribute('aria-expanded', 'true');

  const airportText = route.aggregate
    ? `${(route.origin_codes || []).join('/')} → ${(route.destination_codes || []).join('/')}`
    : `${route.origin || ''} → ${(route.destination_codes || [route.destination]).join('/')}`;
  overlay.querySelector('.mobile-route-calendar-subtitle').textContent =
    `${route.destination_name} · ${route.operating_days}天${airportText.trim() ? ` · ${airportText}` : ''}`;
  overlay.querySelector('.mobile-route-calendar-scroll').innerHTML = routeCalendarHtml(route);

  overlay.hidden = false;
  document.body.classList.add('mobile-calendar-open');
  requestAnimationFrame(() => overlay.classList.add('open'));
}


async function loadOverview() {
  const origin = $('overviewOriginSelect').value.trim() || $('originSelect').value;
  if (!origin) return;
  const p = new URLSearchParams({
    origin,
    membership: $('overviewMembership').value,
    weekday: $('overviewWeekday').value,
    departure_period: $('overviewDeparturePeriod').value,
    airline: $('overviewAirline').value,
    q: $('overviewQuery').value.trim(),
  });
  if (overviewAbortController) overviewAbortController.abort();
  const controller = new AbortController();
  overviewAbortController = controller;
  $('routesTableBody').innerHTML = '<tr><td colspan="6">正在加载…</td></tr>';

  let r;
  try {
    r = await fetch('/api/routes?' + p.toString(), { signal: controller.signal });
  } catch (error) {
    if (error.name === 'AbortError') return;
    throw error;
  }
  if (overviewAbortController !== controller) return;
  overviewAbortController = null;
  const data = await r.json();
  $('routeCount').textContent = `${data.count} 条`;

  $('routesTableBody').innerHTML = data.routes.length ? data.routes.map((x, idx) => {
    const scheduleRows = (x.schedule_rows || []).length
      ? x.schedule_rows
      : (x.flight_nos || []).map((flightNo, rowIndex) => ({
          flight_no: flightNo,
          departure_time: x.times?.[rowIndex]?.departure_time || '',
          arrival_time: x.times?.[rowIndex]?.arrival_time || '',
          cross_day: x.times?.[rowIndex]?.cross_day || 0,
        }));
    const flightTimeHtml = `
      <div class="flight-time-pairs">
        ${scheduleRows.map(row => `
          <div class="flight-time-pair">
            <strong class="flight-pair-no">${esc(row.flight_no)}</strong>
            <span class="flight-pair-time">${esc(row.departure_time)} → ${esc(row.arrival_time)}${row.cross_day ? ' +' + row.cross_day : ''}</span>
          </div>`).join('')}
      </div>`;

    const dateId = `route-dates-${idx}`;
    const airportText = x.aggregate
      ? `${(x.origin_codes || []).map(esc).join('/')} → ${(x.destination_codes || []).map(esc).join('/')}`
      : (x.destination_codes || [x.destination]).map(esc).join('/');

    return `
      <tr class="route-main-row">
        <td class="dest"><div class="dest-title-line"><strong>${esc(x.destination_name)}</strong><span class="route-flight-count">${(x.flight_nos || []).length} 班</span></div><div class="sub">${esc(x.airlines.join(' / '))}</div></td>
        <td>${airportText}</td>
        <td class="flight-time-cell mono">${flightTimeHtml}</td>
        <td><strong>${esc(x.schedule)}</strong></td>
        <td>
          <div class="route-days-line"><strong>${x.operating_days} 天</strong><button type="button" class="date-toggle-btn" data-target="${dateId}" data-route-index="${idx}" aria-expanded="false" title="展开具体日期">▶</button></div>
          <div class="sub">${esc(x.first_date)} ~ ${esc(x.last_date)}</div>
        </td>
        <td>${x.products.map(p => `<span class="tag product">${esc(p)}</span>`).join(' ')}</td>
      </tr>
      <tr class="route-date-row hidden" id="${dateId}">
        <td colspan="6">${routeCalendarHtml(x)}</td>
      </tr>`;
  }).join('') : '<tr><td colspan="6">没有匹配航线</td></tr>';

  $('routesTableBody').querySelectorAll('.date-toggle-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      if (window.matchMedia('(max-width: 640px)').matches) {
        const route = data.routes[Number(btn.dataset.routeIndex)];
        if (route) openMobileRouteCalendarSheet(route, btn);
        return;
      }
      const row = $(btn.dataset.target);
      if (!row) return;
      const opening = row.classList.contains('hidden');
      row.classList.toggle('hidden');
      btn.textContent = opening ? '▼' : '▶';
      btn.setAttribute('aria-expanded', opening ? 'true' : 'false');
      btn.title = opening ? '收起具体日期' : '展开具体日期';
    });
  });
}


document.addEventListener('DOMContentLoaded', () => {
  init().catch(e => alert('初始化失败：' + e.message));

  document.querySelectorAll('.tab').forEach(btn => btn.addEventListener('click', () => {
    document.querySelectorAll('.tab').forEach(x => x.classList.remove('active'));
    document.querySelectorAll('.panel').forEach(x => x.classList.remove('active'));
    btn.classList.add('active');
    $(btn.dataset.tab).classList.add('active');
    if (btn.dataset.tab === 'routesPanel') loadOverview();
  }));

  document.querySelectorAll('#tripMode button').forEach(btn => btn.addEventListener('click', () => {
    document.querySelectorAll('#tripMode button').forEach(x => x.classList.remove('active'));
    btn.classList.add('active');
    tripMode = btn.dataset.mode;
    $('returnField').classList.toggle('hidden', tripMode !== 'roundtrip');
  }));

  $('swapBtn').addEventListener('click', () => {
    const a = $('originSelect').value;
    $('originSelect').value = $('destinationSelect').value;
    $('destinationSelect').value = a;
    refreshAllAirportPickers();
  });
  $('searchBtn').addEventListener('click', searchFlights);
  $('overviewBtn').addEventListener('click', loadOverview);
  $('overviewOriginSelect').addEventListener('change', loadOverview);
  $('overviewMembership').addEventListener('change', loadOverview);
  $('overviewWeekday').addEventListener('change', loadOverview);
  $('overviewDeparturePeriod').addEventListener('change', loadOverview);
  $('overviewAirline').addEventListener('change', loadOverview);
  $('overviewQuery').addEventListener('input', () => {
    clearTimeout(overviewQueryTimer);
    overviewQueryTimer = setTimeout(loadOverview, 250);
  });
  $('overviewQuery').addEventListener('keydown', e => {
    if (e.key === 'Enter') {
      clearTimeout(overviewQueryTimer);
      loadOverview();
    }
  });
});
