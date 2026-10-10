from pathlib import Path
from html import escape

root=Path(__file__).parent
s=['<svg xmlns="http://www.w3.org/2000/svg" width="1720" height="800" viewBox="0 0 1720 800"><rect width="1720" height="800" fill="white"/><defs><marker id="arrow" markerWidth="10" markerHeight="10" refX="9" refY="5" orient="auto"><path d="M0 0L10 5L0 10" fill="#07858A"/></marker></defs><style>text{font-family:Tahoma,Arial,sans-serif;fill:#18334B}</style>']
def arrow(points,dashed=False):
    p=' '.join(f'{x},{y}' for x,y in points)
    s.append(f'<polyline points="{p}" fill="none" stroke="#07858A" stroke-width="3" marker-end="url(#arrow)" '+('stroke-dasharray="10 7"' if dashed else '')+'/>')
def label(x,y,text):
    s.append(f'<text x="{x}" y="{y}" font-size="22" style="fill:#087F83">{escape(text)}</text>')
def box(x,y,w,h,lines,planned=False):
    s.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8" fill="{ "#F3F7F8" if planned else "#F8FBFC" }" stroke="#18334B" stroke-width="2" '+('stroke-dasharray="9 6"' if planned else '')+'/>')
    start=y+h/2-(len(lines)-1)*19
    for i,t in enumerate(lines):
        s.append(f'<text x="{x+w/2}" y="{start+i*38}" dominant-baseline="middle" text-anchor="middle" font-size="{26 if i else 30}" font-weight="{"bold" if i==0 else "normal"}">{escape(t)}</text>')
# Current HTTP / database path.
for a,b in [(265,335),(615,695),(1055,1115),(1365,1445)]:
    arrow([(a,150),(b,150)])
# Services access files directly, separately from relational storage.
arrow([(875,240),(875,345),(1395,345)])
label(915,326,'อ่าน / เขียนไฟล์')
# Vision side branch and its external/local runtime.
arrow([(790,240),(790,500)])
label(805,445,'Image API')
arrow([(995,575),(1135,575)])
label(1008,548,'เรียกโมเดล')
# Future answer adapter integration is intentionally dashed.
arrow([(695,195),(660,195),(660,400),(280,400),(280,500)],True)
label(305,382,'เชื่อม adapter ในอนาคต')
box(15,60,250,180,['Browser','Next.js UI'])
box(335,60,280,180,['FastAPI','REST API','Auth / policy guards'])
box(695,60,360,180,['Services','Auth · Chat · Search','Catalog template adapter'])
box(1115,60,250,180,['Repositories','SQLAlchemy'])
box(1445,60,260,180,['PostgreSQL','pgvector'])
box(1395,290,310,110,['Private storage','ไฟล์รูปภาพ'])
box(100,500,360,150,['Text RAG / LLM','วางแผน'],True)
box(635,500,360,150,['AI / Vision modules','มีโมดูลแล้ว'])
box(1135,500,390,150,['Ollama + Embedding','local / external runtime'])
label(15,725,'เส้นทึบ = เส้นทางปัจจุบันหรือโมดูลที่มีแล้ว • เส้นประ = การเชื่อมที่วางแผน')
s.append('<text x="15" y="768" font-size="26">แชตปัจจุบัน: ค้น products ใน DB → Catalog Template Adapter → บันทึกประวัติ (ยังไม่เรียก LLM)</text></svg>')
(root/'system-architecture.svg').write_text(''.join(s),encoding='utf-8')
