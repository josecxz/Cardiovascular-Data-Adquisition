"""Bring 'Year of preprint publication' (column K) back in line with 'Published Date'
(column L) on the 'Final analytic dataset' sheet.

K is a static value, not a formula, so it did not follow when Published Date was
switched to the v1 dates. This sets K to the 4-digit year of L wherever the two
disagree, and writes it as a NUMBER so sorting, grouping and pivots keep working.

Only mismatched rows are rewritten. Re-running is a no-op.
"""
import re, shutil, zipfile
import xml.etree.ElementTree as ET

WORKBOOK = 'medRxiv and RS CV preprints data analysis 06_30 - Dates Fixed.xlsx'
SHEET = 'xl/worksheets/sheet4.xml'          # 'Final analytic dataset'
DOI_COL, YEAR_COL, PUB_COL = 'B', 'K', 'L'
NS = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'

zin = zipfile.ZipFile(WORKBOOK)
shared = [''.join(t.text or '' for t in si.iter(NS + 't'))
          for si in ET.fromstring(zin.read('xl/sharedStrings.xml'))]
xml = zin.read(SHEET).decode('utf-8')


def cell_text(row_xml, col):
    m = re.search(rf'<c r="{col}\d+"[^>]*?(/>|>(.*?)</c>)', row_xml, re.S)
    if not m or m.group(1) == '/>':
        return ''
    body, opening = m.group(2), m.group(0).split('>', 1)[0]
    if 't="inlineStr"' in opening:
        t = re.search(r'<t[^>]*>(.*?)</t>', body, re.S)
        return t.group(1) if t else ''
    v = re.search(r'<v>(.*?)</v>', body, re.S)
    if not v:
        return ''
    if 't="s"' in opening:
        return shared[int(v.group(1))]
    return v.group(1)


changes, skipped = [], []


def fix_row(m):
    row = m.group(0)
    rnum = int(re.search(r'<row r="(\d+)"', row).group(1))
    if rnum == 1:
        return row
    pub = cell_text(row, PUB_COL).strip()
    if not re.match(r'\d{4}-\d{2}-\d{2}', pub):
        return row
    year = pub[:4]
    old = cell_text(row, YEAR_COL).strip()
    if old[:4] == year:
        return row

    cm = re.search(rf'<c r="{YEAR_COL}{rnum}"([^>]*?)(?:/>|>.*?</c>)', row, re.S)
    if not cm:
        skipped.append((rnum, cell_text(row, DOI_COL)))
        return row
    st = re.search(r'\ss="(\d+)"', cm.group(1))
    st = f' s="{st.group(1)}"' if st else ''
    cell = f'<c r="{YEAR_COL}{rnum}"{st}><v>{year}</v></c>'   # numeric, not text
    changes.append((rnum, cell_text(row, DOI_COL), old, year))
    return row[:cm.start()] + cell + row[cm.end():]


xml, nrows = re.subn(r'<row r="\d+".*?</row>', fix_row, xml, flags=re.S)

tmp = WORKBOOK + '.tmp'
with zipfile.ZipFile(WORKBOOK) as zsrc, zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED) as zout:
    for item in zsrc.infolist():
        data = xml.encode('utf-8') if item.filename == SHEET else zsrc.read(item.filename)
        zout.writestr(item, data)
shutil.move(tmp, WORKBOOK)

print(f'scanned {nrows} rows')
print(f'Year of preprint publication corrected on {len(changes)} rows')
if skipped:
    print(f'  !! no K cell to write on {len(skipped)} rows: {skipped[:5]}')
print('\nfirst 8 (row, DOI, old -> new):')
for r, d, o, n in changes[:8]:
    print(f'   {r:5} {d:32} {o} -> {n}')
