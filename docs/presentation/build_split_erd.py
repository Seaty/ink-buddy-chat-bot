from pathlib import Path
from html import escape

ROOT=Path(__file__).parent
def build(filename,tables,edges,notes):
    s=['<svg xmlns="http://www.w3.org/2000/svg" width="1720" height="800" viewBox="0 0 1720 800"><rect width="1720" height="800" fill="white"/><style>text{font-family:Tahoma,Arial,sans-serif;fill:#18334B}</style>']
    for points,label,lx,ly,dashed in edges:
        coords=' '.join(f'{x},{y}' for x,y in points)
        s.append(f'<polyline points="{coords}" fill="none" stroke="#07858A" stroke-width="3" '+('stroke-dasharray="9 7"' if dashed else '')+'/>')
        s.append(f'<text x="{lx}" y="{ly}" font-size="22" fill="#07858A">{escape(label)}</text>')
        if not dashed:
            ax,ay=points[-2];x,y=points[-1]
            if ax==x:
                z=y-15 if y>ay else y+15
                path=f'M{x-10} {z} L{x} {y} L{x+10} {z}'
            else:
                z=x-15 if x>ax else x+15
                path=f'M{z} {y-10} L{x} {y} L{z} {y+10}'
            s.append(f'<path d="{path}" fill="none" stroke="#07858A" stroke-width="3"/>')
    for name,x,y,purpose,fields in tables:
        s.append(f'<rect x="{x}" y="{y}" width="390" height="270" rx="4" fill="#F8FBFC" stroke="#18334B" stroke-width="2"/><rect x="{x}" y="{y}" width="390" height="55" fill="#18334B"/><text x="{x+17}" y="{y+36}" style="fill:white" font-size="{26 if len(name)<24 else 24}" font-weight="bold">{escape(name)}</text>')
        s.append(f'<text x="{x+17}" y="{y+90}" font-size="23" style="fill:#087F83">{escape(purpose)}</text><path d="M{x+15} {y+108}H{x+375}" stroke="#D4E1E6"/>')
        for i,f in enumerate(fields):
            size=21 if len(f)>29 else 25
            s.append(f'<text x="{x+17}" y="{y+143+i*35}" font-size="{size}">{escape(f)}</text>')
    for i,n in enumerate(notes):
        s.append(f'<text x="15" y="{747+i*33}" font-size="22">{escape(n)}</text>')
    s.append('</svg>')
    (ROOT/filename).write_text(''.join(s),encoding='utf-8')

build('erd-accounts.svg',[
('roles',15,25,'กำหนดสิทธิ์ User / Admin',['PK id : uuid','UK name']),
('users',445,25,'บัญชีและรหัสผ่านผู้ใช้',['PK id : uuid','FK role_id → roles','email / password_hash']),
('guest_sessions',875,25,'Guest token อายุและโควตารูป',['PK id : uuid','FK claimed_by_user_id → users','expires_at / image_uploads_used']),
('audit_logs',1305,25,'บันทึกกิจกรรมของระบบ',['PK id : uuid','FK actor_user_id → users','action / resource_id']),
('password_reset_tokens',15,430,'token สำหรับเปลี่ยนรหัสผ่าน',['PK id : uuid','FK user_id → users','UK token_hash / expires_at']),
('auth_sessions',445,430,'Login session เพื่อ revoke ทันที',['PK id : uuid','FK user_id → users','expires_at / revoked_at']),
('refresh_tokens',875,430,'refresh rotation เก็บเฉพาะ hash',['PK id : uuid','FK (session_id, user_id)*','FK user_id / replaced_by_id**']),
],[
([(405,160),(445,160)],'1:N',408,140,False),
([(640,295),(640,430)],'1 : 0..N',655,365,False),
([(445,270),(420,270),(420,390),(210,390),(210,430)],'1 : 0..N',30,375,False),
([(835,150),(875,150)],'claim',830,330,False),
([(835,575),(875,575)],'1:N*',825,410,False),
([(640,25),(640,5),(1500,5),(1500,25)],'actor: 0..1 user',1305,330,False),
],[
'PK = Primary Key • FK = Foreign Key • 1 : 0..N = หนึ่งรายการสัมพันธ์กับศูนย์หรือหลายรายการ',
'* composite FK → auth_sessions(id,user_id) • ** replaced_by_id → refresh_tokens • UUID ใหม่ใช้ UUIDv7',
])

build('erd-chat-catalog.svg',[
('products',15,25,'ข้อมูลสินค้าและแหล่งอ้างอิง',['PK id : uuid','sku / name / category','price / currency / source_ref']),
('product_image_embeddings',445,25,'เวกเตอร์ภาพสำหรับค้นสินค้า',['PK id : serial','sku — logical link, no FK','embedding : vector(2048)']),
('chat_sessions',875,25,'หัวข้อแชตและเจ้าของ',['PK id : uuid','FK user_id / guest_session_id','title / deleted_at']),
('image_uploads',1305,25,'รูปที่ผู้ใช้แนบและผลวิเคราะห์',['PK id : uuid','FK user_id / guest_session_id','storage_key / analysis']),
('product_images',15,430,'รูปภาพของสินค้าใน catalog',['PK id : uuid','FK product_id → products','storage_key / is_primary']),
('product_embeddings',445,430,'schema เวกเตอร์ข้อความ (แผน RAG)',['PK id : uuid','FK product_id → products','embedding : vector(1024)']),
('chat_messages',875,430,'ข้อความและอ้างอิงสินค้า',['PK id : uuid','FK session_id / image_id','sequence_number / request ID']),
],[
([(210,295),(210,430)],'1 : 0..N',225,365,False),
([(405,270),(420,270),(420,390),(640,390),(640,430)],'1 : 0..N',450,375,False),
([(405,150),(445,150)],'SKU link',398,330,True),
([(1070,295),(1070,430)],'1 : 0..N',1085,365,False),
([(1500,295),(1500,565),(1265,565)],'0..1 image : N messages',1310,410,False),
],[
'Owner XOR: user_id หรือ guest_session_id อย่างใดอย่างหนึ่ง (อ้างอิง users / guest_sessions ในหน้าก่อน)',
'เส้นประ SKU ไม่ใช่ FK • image_id เป็น nullable • product_refs เป็น JSON snapshot ไม่ใช่ FK ไป products',
])
