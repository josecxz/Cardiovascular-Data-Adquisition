"""On the 'Research Square' sheet: copy 'Published Date V1' (column O) into
'Published Date' (column I), then delete column O.

Column O is complete for all 3278 rows -- the v1 date for rows that were a later
version, and the row's own posting date for rows already at v1 -- so it is the source of
truth for the merge. After this the sheet's Published Date matches 'Combined Raw Data'
and 'Final analytic dataset', and the DOIs (all /v1) no longer contradict it.

Re-running is a no-op: once column O is gone there is nothing to merge.
"""
import re, shutil, zipfile
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape

WORKBOOK = 'medRxiv and RS CV preprints data analysis 06_30 - Dates Fixed.xlsx'
SHEET = 'xl/worksheets/sheet1.xml'          # 'Research Square'
PUB_COL, V1_COL = 'I', 'O'
NS = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'

CELL_RE = re.compile(r'<c r="([A-Z]+)(\d+)".*?(?:/>|</c>)', re.S)


def col_index(letters):
    n = 0
    for ch in letters:
        n = n * 26 + (ord(ch) - 64)
    return n


zin = zipfile.ZipFile(WORKBOOK)
shared = [''.join(t.text or '' for t in si.iter(NS + 't'))
          for si in ET.fromstring(zin.read('xl/sharedStrings.xml'))]
xml = zin.read(SHEET).decode('utf-8')

if f'<c r="{V1_COL}1"' not in xml:
    print('column O is already gone - nothing to do')
    raise SystemExit


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


stats = {'copied': 0, 'unchanged': 0, 'inserted': 0, 'no_v1': 0}


def fix_row(m):
    row = m.group(0)
    rnum = int(re.search(r'<row r="(\d+)"', row).group(1))
    row = re.sub(r'spans="1:15"', 'spans="1:14"', row, count=1)

    if rnum > 1:
        v1 = cell_text(row, V1_COL).strip()
        if v1:
            old = cell_text(row, PUB_COL).strip()
            cm = re.search(rf'<c r="{PUB_COL}{rnum}"([^>]*?)(?:/>|>.*?</c>)', row, re.S)
            if cm:
                st = re.search(r'\ss="(\d+)"', cm.group(1))
                st = f' s="{st.group(1)}"' if st else ''
                cell = f'<c r="{PUB_COL}{rnum}"{st} t="inlineStr"><is><t>{escape(v1)}</t></is></c>'
                row = row[:cm.start()] + cell + row[cm.end():]
                stats['copied' if old != v1 else 'unchanged'] += 1
            else:
                # The cell may be absent entirely on rows the source left empty;
                # insert it in column order rather than skipping the row.
                cell = f'<c r="{PUB_COL}{rnum}" t="inlineStr"><is><t>{escape(v1)}</t></is></c>'
                after = next((c for c in CELL_RE.finditer(row)
                              if col_index(c.group(1)) > col_index(PUB_COL)), None)
                row = (row[:after.start()] + cell + row[after.start():] if after
                       else row[:row.rindex('</row>')] + cell + '</row>')
                stats['inserted'] += 1
        else:
            stats['no_v1'] += 1

    # drop the column O cell
    return re.sub(rf'<c r="{V1_COL}{rnum}"[^>]*?(?:/>|>.*?</c>)', '', row, flags=re.S)


xml, nrows = re.subn(r'<row r="\d+".*?</row>', fix_row, xml, flags=re.S)

xml = xml.replace('<dimension ref="A1:O3279"/>', '<dimension ref="A1:N3279"/>', 1)
xml = re.sub(r'<col min="15" max="15"[^/]*/>', '', xml, count=1)
assert '<dimension ref="A1:N3279"/>' in xml and '<col min="15"' not in xml
assert f'<c r="{V1_COL}' not in xml, 'a column O cell survived'

tmp = WORKBOOK + '.tmp'
with zipfile.ZipFile(WORKBOOK) as zsrc, zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED) as zout:
    for item in zsrc.infolist():
        data = xml.encode('utf-8') if item.filename == SHEET else zsrc.read(item.filename)
        zout.writestr(item, data)
shutil.move(tmp, WORKBOOK)

print(f'scanned {nrows} rows')
print(f"   Published Date replaced with the v1 date : {stats['copied']}")
print(f"   already equal to the v1 date             : {stats['unchanged']}")
print(f"   Published Date cell inserted (was absent): {stats['inserted']}")
print(f"   rows with no v1 date to copy             : {stats['no_v1']}")
print('   column O deleted')
