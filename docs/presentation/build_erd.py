from pathlib import Path
from html import escape

out = Path(__file__).with_name('ink-buddy-erd.svg')
parts = ['<svg xmlns="http://www.w3.org/2000/svg" width="1720" height="800" viewBox="0 0 1720 800"><rect width="1720" height="800" fill="white"/><style>text{font-family:Arial,sans-serif;fill:#18334B} .field{font-size:20px} .label{font-size:17px;fill:#087F83}</style>']
tables = [
('roles',30,25,['PK id : uuid','UK name']),
('users',375,25,['PK id : uuid','FK role_id → roles','UK email']),
('guest_sessions',720,25,['PK id : uuid','FK claimed_by_user_id → users','image_uploads_used / expires_at']),
('products',1065,25,['PK id : uuid','sku / name / price / currency']),
('product_image_embeddings',1410,25,['PK id : serial','sku (logical link)','embedding : vector(2048)']),
('password_reset_tokens',30,275,['PK id : uuid','FK user_id → users','UK token_hash']),
('auth_sessions',375,275,['PK id : uuid','FK user_id → users','expires_at / revoked_at']),
('chat_sessions',720,275,['PK id : uuid','FK user_id → users (nullable)','FK guest_session_id (nullable)']),
('product_images',1065,275,['PK id : uuid','FK product_id → products','storage_key']),
('product_embeddings',1410,275,['PK id : uuid','FK product_id → products','embedding : vector(1024)']),
('audit_logs',30,525,['PK id : uuid','FK actor_user_id → users','action / resource_id']),
('refresh_tokens',375,525,['PK id : uuid','FK (session_id, user_id)*','FK user_id / replaced_by_id**']),
('chat_messages',720,525,['PK id : uuid','FK session_id → chat_sessions','FK image_id → image_uploads','sequence_number / client_request_id']),
('image_uploads',1065,525,['PK id : uuid','FK user_id → users (nullable)','FK guest_session_id (nullable)','storage_key / analysis']),
]
def edge(points,label,x,y,dash=False):
    pts=' '.join(f'{a},{b}' for a,b in points)
    parts.append(f'<polyline points="{pts}" fill="none" stroke="#087F83" stroke-width="2.5" '+('stroke-dasharray="7 5" ' if dash else '')+'/>' )
    parts.append(f'<rect x="{x-3}" y="{y-17}" width="{len(label)*10+8}" height="22" fill="white"/><text class="label" x="{x}" y="{y}">{escape(label)}</text>')
    if not dash:
        ax,ay=points[-2];bx,by=points[-1]
        if bx==ax:
            sy=by-12 if by>ay else by+12
            parts.append(f'<path d="M {bx-8} {sy} L {bx} {by} L {bx+8} {sy}" fill="none" stroke="#087F83" stroke-width="2"/>')
        else:
            sx=bx-12 if bx>ax else bx+12
            parts.append(f'<path d="M {sx} {by-8} L {bx} {by} L {sx} {by+8}" fill="none" stroke="#087F83" stroke-width="2"/>')
# FK relationship connectors; compact labels spell out cardinality.
edge([(330,100),(375,100)],'1 : N',333,78)
edge([(525,195),(525,275)],'1 : N',535,238)
edge([(375,155),(350,155),(350,350),(330,350)],'1 : N',335,238)
edge([(375,170),(340,170),(340,600),(330,600)],'0..1 : N',245,500)
edge([(525,445),(525,525)],'1 : N*',535,487)
edge([(675,75),(720,75)],'0..1 : N claim',679,222)
edge([(870,195),(870,275)],'0..1 : N',880,238)
edge([(675,150),(695,150),(695,340),(720,340)],'0..1 : N',597,259)
edge([(870,445),(870,525)],'1 : N',880,488)
edge([(1020,620),(1065,620)],'N : 0..1',1022,500)
edge([(1020,140),(1038,140),(1038,505),(1205,505),(1205,525)],'0..1 : N',1090,493)
edge([(1215,195),(1215,275)],'1 : N',1225,238)
edge([(1365,160),(1387,160),(1387,250),(1560,250),(1560,275)],'1 : N',1445,239)
edge([(1365,90),(1410,90)],'SKU',1368,73,True)
for name,x,y,fields in tables:
    h=170 if len(fields)<4 else 185
    parts.append(f'<rect x="{x}" y="{y}" width="300" height="{h}" rx="5" fill="#F8FBFC" stroke="#18334B" stroke-width="2"/><path d="M{x} {y+40}H{x+300}" stroke="#18334B" stroke-width="1.5"/><text x="{x+12}" y="{y+27}" font-size="{21 if len(name)>23 else 23}" font-weight="bold">{name}</text>')
    for i,f in enumerate(fields):
        size = 16 if len(f) > 32 else (18 if len(f) > 27 else 20)
        parts.append(f'<text class="field" style="font-size:{size}px" x="{x+12}" y="{y+70+i*30}">{escape(f)}</text>')
parts.append('<text x="30" y="748" font-size="20">PK = Primary Key • FK = Foreign Key • N = many • dashed = logical SKU link (no FK)</text>')
parts.append('<text x="30" y="779" font-size="18">Owner XOR: user_id OR guest_session_id • * composite FK → auth_sessions(id,user_id) • ** replaced_by_id → refresh_tokens</text></svg>')
out.write_text(''.join(parts),encoding='utf-8')
print(out.resolve())
