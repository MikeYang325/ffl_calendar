from pathlib import Path


def replace_once(text, old, new, label):
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected 1 occurrence, got {count}")
    return text.replace(old, new, 1)


for file_name in ["static/app.js", "public/static/app.js"]:
    path = Path(file_name)
    text = path.read_text(encoding="utf-8")

    text = replace_once(
        text,
        "let overviewQueryTimer = null;\nconst AIRPORT_PICKERS = {};",
        "let overviewQueryTimer = null;\nlet overviewAbortController = null;\nconst AIRPORT_PICKERS = {};",
        f"{file_name}: abort controller",
    )

    old = '''function airportMatches(item, keyword) {
  if (!keyword) return true;
  const q = keyword.trim().toUpperCase().replace(/\\s+/g, '');
  if (!q) return true;
  return [item.name, item.code, item.label, item.initial, item.search]
    .filter(Boolean)
    .map(v => String(v).toUpperCase().replace(/\\s+/g, ''))
    .some(v => v.includes(q));
}'''
    new = '''function airportMatches(item, keyword) {
  if (!keyword) return true;
  const q = keyword.trim().toUpperCase().replace(/\\s+/g, '');
  if (!q) return true;
  return (item._searchKey || '').includes(q);
}'''
    text = replace_once(text, old, new, f"{file_name}: cached airport search key")

    old = '''  const state = {
    picker, select, input, dropdown, search, clearBtn, closeBtn,
    tabs, grid, resultTitle, activeTab: 'hot',
  };'''
    new = '''  const state = {
    picker, select, input, dropdown, search, clearBtn, closeBtn,
    tabs, grid, resultTitle, activeTab: 'hot',
    hotItems: null, lastRenderKey: null, renderedTabsFor: null, prewarmed: false,
  };'''
    text = replace_once(text, old, new, f"{file_name}: picker state cache")

    old = '''  function hotAirports() {
    const byCode = new Map((META.airports || []).map(x => [x.code, x]));
    const hot = HOT_AIRPORT_CODES.map(c => byCode.get(c)).filter(Boolean);
    if (hot.length >= 12) return hot;
    const seen = new Set(hot.map(x => x.code));
    for (const item of (META.airports || [])) {
      if (!seen.has(item.code)) {
        hot.push(item);
        seen.add(item.code);
      }
      if (hot.length >= 30) break;
    }
    return hot;
  }'''
    new = '''  function hotAirports() {
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
  }'''
    text = replace_once(text, old, new, f"{file_name}: hot airport cache")

    old = '''  function renderTabs() {
    tabs.innerHTML = AIRPORT_TAB_GROUPS.map(tab => `
      <button type="button" role="tab"
              class="airport-tab ${state.activeTab === tab.key ? 'active' : ''}"
              data-tab="${esc(tab.key)}">${esc(tab.label)}</button>
    `).join('');
  }'''
    new = '''  function renderTabs() {
    if (state.renderedTabsFor === state.activeTab && tabs.childElementCount) return;
    tabs.innerHTML = AIRPORT_TAB_GROUPS.map(tab => `
      <button type="button" role="tab"
              class="airport-tab ${state.activeTab === tab.key ? 'active' : ''}"
              data-tab="${esc(tab.key)}">${esc(tab.label)}</button>
    `).join('');
    state.renderedTabsFor = state.activeTab;
  }'''
    text = replace_once(text, old, new, f"{file_name}: tab render cache")

    old = '''  function render() {
    const keyword = search.value.trim();
    clearBtn.hidden = !keyword;

    if (keyword) {'''
    new = '''  function render() {
    const keyword = search.value.trim();
    const renderKey = `${state.activeTab}\\u0000${keyword}`;
    clearBtn.hidden = !keyword;
    if (state.lastRenderKey === renderKey) return;
    state.lastRenderKey = renderKey;

    if (keyword) {'''
    text = replace_once(text, old, new, f"{file_name}: render dedupe")

    old = '''  window.addEventListener('resize', () => {
    if (!dropdown.hidden) {
      picker.classList.remove('align-right');
      const r = dropdown.getBoundingClientRect();
      if (r.right > window.innerWidth - 8) picker.classList.add('align-right');
    }
  });
}'''
    new = '''  window.addEventListener('resize', () => {
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
}'''
    text = replace_once(text, old, new, f"{file_name}: picker prewarm hook")

    old = '''function setDefaultAirports() {'''
    new = '''function prewarmAirportPickers() {
  const run = () => Object.values(AIRPORT_PICKERS).forEach(picker => picker.prewarm?.());
  if ('requestIdleCallback' in window) {
    window.requestIdleCallback(run, { timeout: 200 });
  } else {
    setTimeout(run, 16);
  }
}

function setDefaultAirports() {'''
    text = replace_once(text, old, new, f"{file_name}: prewarm scheduler")

    old = '''  const res = await fetch('/api/meta');
  META = await res.json();
  $('dataBadge').textContent = `数据 ${META.date_min} → ${META.date_max}`;'''
    new = '''  const res = await fetch('/api/meta');
  META = await res.json();
  (META.airports || []).forEach(item => {
    item._searchKey = [item.name, item.code, item.label, item.initial, item.search]
      .filter(Boolean)
      .map(v => String(v).toUpperCase().replace(/\\s+/g, ''))
      .join('|');
  });
  (META.cities || []).forEach(city => {
    city._searchKey = [city.name, city.label, ...(city.codes || [])]
      .filter(Boolean)
      .map(v => String(v).toUpperCase().replace(/\\s+/g, ''))
      .join('|');
  });
  $('dataBadge').textContent = `数据 ${META.date_min} → ${META.date_max}`;'''
    text = replace_once(text, old, new, f"{file_name}: build search index")

    old = '''  setDefaultAirports();
  renderStats();
  loadOverview();'''
    new = '''  setDefaultAirports();
  prewarmAirportPickers();
  renderStats();
  loadOverview();'''
    text = replace_once(text, old, new, f"{file_name}: schedule prewarm")

    old = '''      const matchedCities = allowCities ? (META.cities || [])
        .filter(city => [city.name, city.label, ...(city.codes || [])]
          .some(v => String(v || '').toUpperCase().replace(/\\s+/g, '').includes(normalized)))'''
    new = '''      const matchedCities = allowCities ? (META.cities || [])
        .filter(city => (city._searchKey || '').includes(normalized))'''
    text = replace_once(text, old, new, f"{file_name}: cached city search key")

    old = '''  $('routesTableBody').innerHTML = '<tr><td colspan="7">正在加载…</td></tr>';
  const r = await fetch('/api/routes?' + p.toString());
  const data = await r.json();'''
    new = '''  if (overviewAbortController) overviewAbortController.abort();
  const controller = new AbortController();
  overviewAbortController = controller;
  $('routesTableBody').innerHTML = '<tr><td colspan="7">正在加载…</td></tr>';

  let r;
  try {
    r = await fetch('/api/routes?' + p.toString(), { signal: controller.signal });
  } catch (error) {
    if (error.name === 'AbortError') return;
    throw error;
  }
  if (overviewAbortController !== controller) return;
  overviewAbortController = null;
  const data = await r.json();'''
    text = replace_once(text, old, new, f"{file_name}: cancel stale overview request")

    path.write_text(text, encoding="utf-8")


for file_name in ["static/style.css", "public/static/style.css"]:
    path = Path(file_name)
    text = path.read_text(encoding="utf-8")
    text = replace_once(
        text,
        '''  box-shadow:0 18px 48px rgba(28,52,82,.20); overflow:hidden;\n}''',
        '''  box-shadow:0 18px 48px rgba(28,52,82,.20); overflow:hidden;\n  contain:layout paint;\n}''',
        f"{file_name}: dropdown containment",
    )
    text = replace_once(
        text,
        '.airport-content { max-height:340px; overflow:auto; padding:16px 18px 18px; }',
        '.airport-content { max-height:340px; overflow:auto; padding:16px 18px 18px; contain:layout paint; }',
        f"{file_name}: content containment",
    )
    path.write_text(text, encoding="utf-8")

print("airport picker performance patch applied")
