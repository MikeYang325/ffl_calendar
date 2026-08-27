from pathlib import Path

OLD = '${x.flight_records_count} 班'
NEW = '${(x.flight_nos || []).length} 班'

for file_name in ['static/app.js', 'public/static/app.js']:
    path = Path(file_name)
    text = path.read_text(encoding='utf-8')
    count = text.count(OLD)
    if count != 1:
        raise SystemExit(f'{file_name}: expected exactly one old flight count expression, got {count}')
    text = text.replace(OLD, NEW, 1)
    if text.count(NEW) != 1:
        raise SystemExit(f'{file_name}: dynamic flight count expression not applied exactly once')
    path.write_text(text, encoding='utf-8')

print('dynamic flight count patch applied')
