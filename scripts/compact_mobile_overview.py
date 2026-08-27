from pathlib import Path

MARKER = "/* mobile compact overview v1 */"
BLOCK = r'''

/* mobile compact overview v1 */
@media (max-width: 520px) {
  .hero {
    padding: 22px 14px 44px;
  }
  .hero h1 {
    margin: 7px 0 6px;
    font-size: 27px;
    line-height: 1.12;
  }
  .eyebrow {
    font-size: 10px;
    letter-spacing: .16em;
  }
  .data-badge {
    margin-top: 11px;
    padding: 7px 11px;
    font-size: 11px;
  }
  .container {
    padding: 0 10px;
    margin-top: -27px;
  }
  .main-tabs {
    gap: 6px;
    margin-bottom: 10px;
  }
  .tab {
    padding: 10px 16px;
    border-radius: 11px;
    font-size: 14px;
  }

  .route-overview-controls {
    padding: 14px 14px 15px;
    border-radius: 16px;
  }
  .overview-title {
    gap: 10px;
  }
  .overview-title h2 {
    font-size: 21px;
  }
  .route-count {
    font-size: 23px;
    white-space: nowrap;
  }

  .overview-filter-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 9px 8px;
    margin-top: 10px;
  }
  .overview-filter-grid .field {
    min-width: 0;
    gap: 4px;
  }
  .overview-filter-grid .field > span {
    font-size: 11px;
    line-height: 1.2;
  }
  .overview-filter-grid .field input,
  .overview-filter-grid .field select,
  .route-overview-controls .airport-input {
    height: 40px;
    min-width: 0;
    padding-left: 10px;
    padding-right: 10px;
    border-radius: 10px;
    font-size: 14px;
  }
  .route-overview-controls .airport-input {
    padding-right: 30px;
  }
  .route-overview-controls .airport-picker::after {
    right: 10px;
    top: 9px;
  }
  .route-overview-controls .primary-btn.secondary {
    margin-top: 12px;
    min-height: 40px;
    padding: 10px 18px;
    border-radius: 11px;
    font-size: 14px;
  }

  .table-card {
    margin-top: 12px;
  }
}
'''

for name in ("static/style.css", "public/static/style.css"):
    path = Path(name)
    text = path.read_text(encoding="utf-8")
    if MARKER not in text:
        path.write_text(text.rstrip() + BLOCK + "\n", encoding="utf-8")
