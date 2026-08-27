from pathlib import Path

CSS = r'''

/* mobile information-density optimization v3 */
@media (max-width: 520px) {
  /* Search form: keep all fields, reduce chrome and vertical dead space. */
  #searchPanel .search-card {
    padding: 10px 11px 11px;
    border-radius: 14px;
  }
  #searchPanel .segmented {
    margin-bottom: 7px;
    padding: 2px;
    border-radius: 9px;
  }
  #searchPanel .segmented button {
    min-height: 30px;
    padding: 5px 14px;
    border-radius: 7px;
    font-size: 12px;
  }
  #searchPanel .search-grid { gap: 6px; }
  #searchPanel .route-row {
    gap: 6px;
  }
  #searchPanel .field { gap: 3px; }
  #searchPanel .field > span {
    font-size: 10px;
    line-height: 1.15;
  }
  #searchPanel .field input,
  #searchPanel .field select,
  #searchPanel .airport-input {
    height: 36px;
    padding-left: 8px;
    padding-right: 8px;
    border-radius: 9px;
    font-size: 12px;
  }
  #searchPanel .airport-input { padding-right: 25px; }
  #searchPanel .airport-picker::after {
    right: 8px;
    top: 7px;
    font-size: 13px;
  }
  #searchPanel .route-row .swap-btn {
    top: 25px;
    width: 26px;
    height: 26px;
    font-size: 13px;
    border-width: 1px;
  }
  #searchPanel .options-row,
  #searchPanel .advanced-grid {
    gap: 6px;
    margin-top: 6px;
  }
  #searchPanel .advanced {
    margin-top: 7px;
    padding-top: 6px;
  }
  #searchPanel .advanced summary {
    font-size: 11px;
    line-height: 1.2;
  }
  #searchPanel .primary-btn {
    margin-top: 8px;
    min-height: 38px;
    padding: 8px 12px;
    border-radius: 10px;
    font-size: 13px;
  }

  /* KPI strip: shallower cards, same information. */
  #searchPanel .stats-grid {
    gap: 5px;
    margin: 7px 0;
  }
  #searchPanel .stat {
    min-height: 48px;
    padding: 6px 4px 5px;
    border-radius: 10px;
  }
  #searchPanel .stat strong {
    margin-top: 1px;
    font-size: 16px;
    line-height: 1.05;
  }
  #searchPanel .stat span {
    font-size: 8px;
    line-height: 1.05;
  }

  /* Result heading: remove oversized gaps between query summary and cards. */
  #searchPanel .results-section {
    margin-top: 8px;
  }
  #searchPanel .section-heading {
    padding: 0 3px 5px;
  }
  #searchPanel .section-heading h2 {
    font-size: 18px;
    line-height: 1.2;
  }
  #searchPanel .section-heading p {
    margin-top: 3px;
    font-size: 10px;
    line-height: 1.25;
  }
  #searchPanel .return-heading {
    margin-top: 13px;
  }
  #searchPanel .results-list {
    gap: 8px;
  }

  /* Flight cards: horizontal header + tighter time axis, without dropping data. */
  #searchPanel .flight-card {
    padding: 11px 12px 10px;
    border-radius: 14px;
    box-shadow: 0 5px 15px rgba(73, 31, 38, .05);
  }
  #searchPanel .flight-card-head {
    flex-direction: row;
    align-items: center;
    justify-content: space-between;
    gap: 7px;
    padding-bottom: 7px;
  }
  #searchPanel .flight-card-head > div:first-child {
    min-width: 0;
  }
  #searchPanel .flight-card-head > div:first-child > strong {
    display: block;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-size: 14px;
    line-height: 1.2;
  }
  #searchPanel .flight-summary {
    margin-top: 1px;
    font-size: 9px;
    line-height: 1.2;
  }
  #searchPanel .tags {
    flex: 0 0 auto;
    flex-wrap: nowrap;
    gap: 4px;
  }
  #searchPanel .tag {
    padding: 3px 6px;
    font-size: 9px;
    line-height: 1.1;
  }
  #searchPanel .segment {
    grid-template-columns: 72px minmax(0, 1fr) 72px;
    gap: 6px;
    padding: 10px 0 7px;
  }
  #searchPanel .time-block strong {
    font-size: 20px;
    line-height: 1.05;
  }
  #searchPanel .time-block span {
    margin-top: 2px;
    font-size: 9px;
    line-height: 1.2;
  }
  #searchPanel .timeline {
    gap: 5px;
    font-size: 9px;
    white-space: nowrap;
  }
  #searchPanel .timeline .plane {
    font-size: 14px;
  }
  #searchPanel .segment-meta {
    gap: 3px 7px;
    margin-top: -2px;
    font-size: 9px;
    line-height: 1.25;
  }
  #searchPanel .connection {
    margin: -1px 0;
    padding: 5px 8px;
    border-radius: 7px;
    font-size: 9px;
  }
}
'''

for name in ('static/style.css', 'public/static/style.css'):
    p = Path(name)
    text = p.read_text(encoding='utf-8')
    marker = '/* mobile information-density optimization v3 */'
    if marker not in text:
        p.write_text(text.rstrip() + CSS + '\n', encoding='utf-8')

print('mobile density patch applied')
