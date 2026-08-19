"""Set 'Published Date' to the collected v1 date on the analysis sheets, for the
Research Square rows whose DOI names a version later than v1.

Two sheets are updated in place:

    Final analytic dataset  column L   453 rows
    Combined Raw Data       column I   472 rows (+ 18 blank v1 rows filled)

Research Square rows are identified by the '10.21203/' DOI prefix rather than the
Source column, because 13 rows on 'Combined Raw Data' have an empty Source cell.

Rows on other sheets, medRxiv rows and rows already at /v1 are left alone. Dependent
columns on 'Final analytic dataset' (M, N, O, P, Z) are formulas over Published Date, so
fullCalcOnLoad is set to make Excel recompute them on open.

NOTE: 'Year of preprint publication' (column K on the final sheet) is a static value, not
a formula. It is deliberately not touched; the report at the end lists how many rows it
is now stale on.

Re-running is a no-op: the same v1 date is written each time.
"""
import json, re, shutil, zipfile
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape

WORKBOOK = 'medRxiv and RS CV preprints data analysis 06_30 - Dates Fixed.xlsx'
RS_PREFIX = '10.21203/'
NS = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
VER = re.compile(r'/v(\d+)\s*$')
CELL_RE = re.compile(r'<c r="([A-Z]+)(\d+)".*?(?:/>|</c>)', re.S)

TARGETS = [
    # part,                        sheet name,               doi, pub, year, fill blank v1
    ('xl/worksheets/sheet4.xml', 'Final analytic dataset', 'B', 'L', 'K', False),
    ('xl/worksheets/sheet3.xml', 'Combined Raw Data',      'B', 'I', None, True),
]

cache = json.load(open('v1_dates_cache.json'))
v1_dates = {doi: rec['v1_date'] for doi, rec in cache.items() if rec.get('v1_date')}

zin = zipfile.ZipFile(WORKBOOK)
shared = [''.join(t.text or '' for t in si.iter(NS + 't'))
          for si in ET.fromstring(zin.read('xl/sharedStrings.xml'))]


def col_index(letters):
    n = 0
    for ch in letters:
        n = n * 26 + (ord(ch) - 64)
    return n


def cell_text(row_xml, col):
    m = re.search(rf'<c r="{col}\d+"[^>]*?(/>|>(.*?)</c>)', row_xml, re.S)
    if not m or m.group(1) == '/>':
        return ''
    body, opening = m.group(2), m.group(0).split('>', 1)[0]
    if 't="inlineStr"' in opening:                  # cells this script wrote earlier
        t = re.search(r'<t[^>]*>(.*?)</t>', body, re.S)
        return t.group(1) if t else ''
    v = re.search(r'<v>(.*?)</v>', body, re.S)
    if not v:
        return ''
    if 't="s"' in opening:
        return shared[int(v.group(1))]
    return v.group(1)


def set_cell(row, col, rnum, text):
    """Replace the cell at col/rnum, or insert it in column order if absent."""
    m = re.search(rf'<c r="{col}{rnum}"([^>]*?)(?:/>|>.*?</c>)', row, re.S)
    if m:
        style = re.search(r'\ss="(\d+)"', m.group(1))
        style = f' s="{style.group(1)}"' if style else ''
        cell = f'<c r="{col}{rnum}"{style} t="inlineStr"><is><t>{escape(text)}</t></is></c>'
        return row[:m.start()] + cell + row[m.end():]
    cell = f'<c r="{col}{rnum}" t="inlineStr"><is><t>{escape(text)}</t></is></c>'
    after = next((c for c in CELL_RE.finditer(row)
                  if col_index(c.group(1)) > col_index(col)), None)
    if after:
        return row[:after.start()] + cell + row[after.start():]
    return row[:row.rindex('</row>')] + cell + '</row>'


parts, report = {}, []
for part, name, doi_col, pub_col, year_col, fill_blank in TARGETS:
    xml = zin.read(part).decode('utf-8')
    stats = {'updated': 0, 'unchanged': 0, 'blank_filled': 0}
    year_stale = []

    def fix_row(m, doi_col=doi_col, pub_col=pub_col, year_col=year_col,
                fill_blank=fill_blank, stats=stats, year_stale=year_stale):
        row = m.group(0)
        rnum = int(re.search(r'<row r="(\d+)"', row).group(1))
        if rnum == 1:
            return row
        doi = cell_text(row, doi_col).strip()
        if not doi.startswith(RS_PREFIX):
            return row
        ver = VER.search(doi)
        if not ver:
            return row
        new = v1_dates.get(doi)
        if not new:
            return row
        old = cell_text(row, pub_col).strip()

        if int(ver.group(1)) != 1:
            if old == new:
                stats['unchanged'] += 1
                return row
            stats['updated'] += 1
        elif fill_blank and not old:
            stats['blank_filled'] += 1
        else:
            return row

        row = set_cell(row, pub_col, rnum, new)
        if year_col:
            y = cell_text(row, year_col).strip()
            if y and y[:4] != new[:4]:
                year_stale.append((rnum, doi, y, new[:4]))
        return row

    xml, nrows = re.subn(r'<row r="\d+".*?</row>', fix_row, xml, flags=re.S)
    parts[part] = xml.encode('utf-8')
    report.append((name, pub_col, nrows, stats, year_stale))

# Dependent columns are formulas; make Excel recompute them on open.
wbx = zin.read('xl/workbook.xml').decode('utf-8')
if 'fullCalcOnLoad' not in wbx:
    wbx = re.sub(r'<calcPr([^/]*)/>', r'<calcPr\1 fullCalcOnLoad="1"/>', wbx, count=1)
assert 'fullCalcOnLoad="1"' in wbx
parts['xl/workbook.xml'] = wbx.encode('utf-8')

tmp = WORKBOOK + '.tmp'
with zipfile.ZipFile(WORKBOOK) as zsrc, zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED) as zout:
    for item in zsrc.infolist():
        zout.writestr(item, parts.get(item.filename) or zsrc.read(item.filename))
shutil.move(tmp, WORKBOOK)

for name, pub_col, nrows, stats, year_stale in report:
    print(f'{name!r} (column {pub_col}) - {nrows} rows scanned')
    print(f'   set to v1 date : {stats["updated"]}')
    print(f'   already correct: {stats["unchanged"]}')
    print(f'   blanks filled  : {stats["blank_filled"]}')
    if year_stale:
        print(f'   !! year column now stale on {len(year_stale)} rows')
    print()
