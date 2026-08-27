from pathlib import Path


def patch_js(path):
    p = Path(path)
    text = p.read_text(encoding='utf-8')

    anchor = '''function routeCalendarHtml(route) {'''
    if anchor not in text:
        raise SystemExit(f'missing routeCalendarHtml in {path}')

    insert_after = '''function routeCalendarHtml(route) {'''
    # Functions are inserted before loadOverview so routeCalendarHtml stays unchanged.
    marker = '''\n\nasync function loadOverview() {'''
    mobile_funcs = r'''

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
'''
    if 'function ensureMobileRouteCalendarSheet()' not in text:
        if marker not in text:
            raise SystemExit(f'missing loadOverview marker in {path}')
        text = text.replace(marker, mobile_funcs + marker, 1)

    old_button = '''<button type="button" class="date-toggle-btn" data-target="${dateId}" aria-expanded="false" title="展开具体日期">▶</button>'''
    new_button = '''<button type="button" class="date-toggle-btn" data-target="${dateId}" data-route-index="${idx}" aria-expanded="false" title="展开具体日期">▶</button>'''
    if old_button in text:
        text = text.replace(old_button, new_button, 1)
    elif 'data-route-index="${idx}"' not in text:
        raise SystemExit(f'missing date button in {path}')

    old_listener = '''  $('routesTableBody').querySelectorAll('.date-toggle-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const row = $(btn.dataset.target);
      if (!row) return;
      const opening = row.classList.contains('hidden');
      row.classList.toggle('hidden');
      btn.textContent = opening ? '▼' : '▶';
      btn.setAttribute('aria-expanded', opening ? 'true' : 'false');
      btn.title = opening ? '收起具体日期' : '展开具体日期';
    });
  });'''
    new_listener = '''  $('routesTableBody').querySelectorAll('.date-toggle-btn').forEach(btn => {
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
  });'''
    if old_listener in text:
        text = text.replace(old_listener, new_listener, 1)
    elif "openMobileRouteCalendarSheet(route, btn)" not in text:
        raise SystemExit(f'missing date listener in {path}')

    p.write_text(text, encoding='utf-8')


def patch_css(path):
    p = Path(path)
    text = p.read_text(encoding='utf-8')
    marker = '/* compact mobile route calendar sheet v1 */'
    if marker in text:
        return

    css = r'''

/* compact mobile route calendar sheet v1 */
.mobile-route-calendar-overlay {
  position:fixed;
  inset:0;
  z-index:1000;
  display:flex;
  align-items:flex-end;
  justify-content:center;
  background:rgba(31,22,26,.36);
  opacity:0;
  transition:opacity .18s ease;
  overscroll-behavior:contain;
}
.mobile-route-calendar-overlay[hidden] { display:none !important; }
.mobile-route-calendar-overlay.open { opacity:1; }
.mobile-route-calendar-sheet {
  width:100%;
  max-width:640px;
  max-height:min(78vh,680px);
  display:flex;
  flex-direction:column;
  overflow:hidden;
  background:#fffdfb;
  border-radius:18px 18px 0 0;
  box-shadow:0 -14px 42px rgba(62,21,29,.18);
  transform:translateY(100%);
  transition:transform .18s ease;
}
.mobile-route-calendar-overlay.open .mobile-route-calendar-sheet { transform:translateY(0); }
.mobile-route-calendar-head {
  flex:0 0 auto;
  min-height:54px;
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap:12px;
  padding:10px 14px 9px 16px;
  border-bottom:1px solid #eee4df;
  background:#fffdfb;
}
.mobile-route-calendar-head > div {
  min-width:0;
  display:flex;
  align-items:baseline;
  gap:8px;
  overflow:hidden;
}
.mobile-route-calendar-head strong {
  flex:0 0 auto;
  font-size:15px;
  color:var(--ink);
}
.mobile-route-calendar-subtitle {
  min-width:0;
  overflow:hidden;
  text-overflow:ellipsis;
  white-space:nowrap;
  font-size:11px;
  color:var(--muted);
}
.mobile-route-calendar-close {
  flex:0 0 auto;
  width:32px;
  height:32px;
  padding:0;
  border:0;
  border-radius:50%;
  background:#f4ece8;
  color:#725c61;
  font-size:22px;
  line-height:1;
}
.mobile-route-calendar-scroll {
  flex:1 1 auto;
  overflow:auto;
  -webkit-overflow-scrolling:touch;
  overscroll-behavior:contain;
  background:#fff;
}
body.mobile-calendar-open { overflow:hidden; }

@media (max-width:640px) {
  /* 手机上展开详情使用独立底部月历，表格里的详情行始终不展开。 */
  .routes-table .route-date-row { display:none !important; }

  .mobile-route-calendar-scroll .route-date-panel {
    padding:0;
    background:#fff;
  }
  .mobile-route-calendar-scroll .simple-route-legend {
    display:none;
  }
  .mobile-route-calendar-scroll .route-calendars {
    display:block;
  }
  .mobile-route-calendar-scroll .route-calendar-month {
    padding:12px 12px 14px;
    border:0;
    border-radius:0;
    background:#fff;
  }
  .mobile-route-calendar-scroll .route-calendar-month + .route-calendar-month {
    border-top:7px solid #f5f1ed;
  }
  .mobile-route-calendar-scroll .calendar-month-title {
    margin:1px 0 8px;
    text-align:center;
    color:#35272b;
    font-size:14px;
    font-weight:800;
  }
  .mobile-route-calendar-scroll .calendar-weekdays,
  .mobile-route-calendar-scroll .calendar-days {
    grid-template-columns:repeat(7,minmax(0,1fr));
    gap:0;
  }
  .mobile-route-calendar-scroll .calendar-weekdays {
    margin:0 0 2px;
    color:#91858a;
    font-size:10px;
    font-weight:650;
  }
  .mobile-route-calendar-scroll .calendar-weekdays span {
    height:24px;
    display:flex;
    align-items:center;
    justify-content:center;
  }
  .mobile-route-calendar-scroll .calendar-day {
    position:relative;
    aspect-ratio:auto;
    min-height:31px;
    height:31px;
    padding:0;
    border:0 !important;
    border-radius:0;
    background:transparent !important;
    font-size:12px;
    line-height:31px;
  }
  .mobile-route-calendar-scroll .calendar-day.route-on {
    color:var(--primary);
    font-weight:800;
  }
  .mobile-route-calendar-scroll .calendar-day.route-on::after {
    content:"";
    position:absolute;
    left:50%;
    bottom:2px;
    width:4px;
    height:4px;
    margin-left:-2px;
    border-radius:50%;
    background:var(--primary);
  }
  .mobile-route-calendar-scroll .calendar-day.route-off {
    color:#a8a0a3;
    font-weight:500;
  }
  .mobile-route-calendar-scroll .calendar-day.outside,
  .mobile-route-calendar-scroll .calendar-day.blank {
    color:#ded9db;
    font-weight:400;
  }
}
'''
    p.write_text(text.rstrip() + css + '\n', encoding='utf-8')


for f in ('static/app.js', 'public/static/app.js'):
    patch_js(f)
for f in ('static/style.css', 'public/static/style.css'):
    patch_css(f)

print('mobile calendar patch applied')
