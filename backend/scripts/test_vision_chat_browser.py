"""One paid Vision + Text RAG browser trial; public catalog only, disposable DB.

Copies product facts/vectors, never accounts/history, from the local catalog.
Does not change main DB or the team's image embedding configuration.
"""
import json,os,shutil,socket,subprocess,sys,time,tempfile
from pathlib import Path
from datetime import datetime,timezone
import httpx,psycopg
from psycopg import sql
from sqlalchemy import create_engine,text
from sqlalchemy.engine import make_url,URL
from app.core.config import Settings
from app.core.identifiers import uuid7
from app.services.session.openrouter_adapter import catalog_evidence

BROWSER=r'''
const {chromium}=require(require.resolve('@playwright/test',{paths:[process.cwd()]}));
const assert=require('node:assert/strict');const fs=require('node:fs');
(async()=>{
const browser=await chromium.launch({channel:'msedge'});const page=await browser.newPage({viewport:{width:390,height:844}});
page.setDefaultTimeout(70000);
try{
 await page.route('http://localhost:8000/api/v1/**',async route=>{
  // Keep the browser's original multipart file stream; route.fetch's copied
  // request body may omit Chromium file contents.
  if(route.request().method()==='POST'&&new URL(route.request().url()).pathname==='/api/v1/images'){
   await route.continue({url:route.request().url().replace('localhost:8000','localhost:8001')});return;
  }
  try{const response=await route.fetch({url:route.request().url().replace('localhost:8000','localhost:8001'),timeout:65000});await route.fulfill({response});}
  catch{await route.abort('timedout');}
 });
 await page.goto('http://localhost:3000/chat');
 await page.getByLabel('เลือกรูปเครื่องเขียน').setInputFiles(process.env.VISION_TEST_IMAGE);
 await page.getByAltText('รูปที่เลือกแนบ').waitFor();
 await page.getByLabel('ร่างคำถามของคุณ').fill('มีสินค้านี้ไหม');
 const pending=page.waitForResponse(r=>r.request().method()==='POST'&&/\/chat-sessions\/[^/]+\/messages$/.test(new URL(r.url()).pathname));
 pending.catch(()=>{});
 const uploading=page.waitForResponse(r=>r.request().method()==='POST'&&new URL(r.url()).pathname==='/api/v1/images');
 await page.getByRole('button',{name:'ส่งข้อความ',exact:true}).click();
 const upload=await uploading;
 if(upload.status()!==201){fs.writeFileSync(process.env.VISION_TEST_REPORT,JSON.stringify({status:'failed',stage:'upload',http_status:upload.status(),error:await upload.json()},null,2));throw new Error('Upload failed');}
 const response=await pending;const pair=await response.json();
 const report={tested_at:new Date().toISOString(),status:'failed',http_status:response.status(),transport:'real browser -> isolated HTTP API -> disposable PostgreSQL -> OpenRouter Vision + existing text embeddings',public_test_image:process.env.VISION_TEST_IMAGE.split(/[\\/]/).pop(),pair};
 fs.writeFileSync(process.env.VISION_TEST_REPORT,JSON.stringify(report,null,2));
 assert.equal(response.status(),201);
 assert(pair.user_message.image_id);assert(pair.assistant_message.product_refs.length>0);
 assert(pair.assistant_message.product_refs.every(p=>p.match_method==='vision_text_catalog'&&p.match_type==='similar'));
 await page.getByLabel('สินค้าที่เกี่ยวข้อง').waitFor();
 await page.getByAltText('รูปที่แนบกับข้อความ').waitFor();
 await page.reload();await page.getByAltText('รูปที่แนบกับข้อความ').waitFor();
 await page.getByLabel('สินค้าที่เกี่ยวข้อง').waitFor();
 assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
 await page.screenshot({path:process.env.VISION_TEST_SCREENSHOT,fullPage:true});
 report.checks=['upload_with_prompt','real_vision_and_retrieval','catalog_references','similar_not_exact','private_preview','reload_history','mobile_no_overflow'];
 report.status='passed';
 fs.writeFileSync(process.env.VISION_TEST_REPORT,JSON.stringify(report,null,2));
 console.log('Real Vision chat browser: PASS');
}finally{await browser.close();}
})().catch(error=>{console.error(error.name+': Vision smoke failed; see report without dumping request headers');process.exitCode=1});
'''

def main():
    root=Path(__file__).resolve().parents[2];settings=Settings()
    with socket.socket() as probe:probe.bind(('127.0.0.1',8001))
    manifest=json.loads((root/'backend/datasets/reviewed_catalog.json').read_text(encoding='utf-8'))['products']
    source=create_engine(settings.database_url)
    with source.connect() as conn:
        products=[dict(row) for row in conn.execute(text('SELECT * FROM products')).mappings()]
        embeddings=[dict(row) for row in conn.execute(text('SELECT id,product_id,model_name,source_text,embedding::text AS embedding FROM product_embeddings')).mappings()]
    source.dispose();approved={p['sku']:p for p in manifest}
    # Compare only fields actually sent externally. Never copy account tables.
    for row in products:
        public=approved[row['sku']]
        public={**public,'id':row['id'],'availability':public.get('availability')}
        from decimal import Decimal
        if public.get('price') is not None:
            assert Decimal(str(public['price']))==row['price']
            public['price']=row['price'] # compare the same SQL numeric formatting
        assert catalog_evidence([row])==catalog_evidence([public]),'DB facts differ from reviewed public manifest'
    image=root/'backend/datasets/catalog/ballpoint_pen/monami_flip_07_pastel_green.jpg'
    assert image.is_file() and image.resolve().is_relative_to(root)
    name='ink_buddy_test_'+uuid7().hex;dburl=make_url(settings.database_url)
    params=dict(host=dburl.host,port=dburl.port,user=dburl.username,password=dburl.password,dbname=dburl.database)
    process=None;folder=root/'.local/vision-chat-smoke';folder.mkdir(parents=True,exist_ok=True)
    report=root/'docs/report/VISION_CHAT_BROWSER.json';script=folder/'browser.cjs';script.write_text(BROWSER,encoding='utf-8')
    with psycopg.connect(**params,autocommit=True) as admin:
        admin.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
        try:
            target=URL.create('postgresql+psycopg',username=params['user'],password=params['password'],host=params['host'],port=params['port'],database=name).render_as_string(hide_password=False)
            with psycopg.connect(**{**params,'dbname':name},autocommit=True) as conn:conn.execute((root/'database/ddl/001_init.sql').read_text(encoding='utf-8'))
            engine=create_engine(target)
            with engine.begin() as conn:
                for row in products:
                    conn.execute(text('INSERT INTO products(id,sku,name,category,brand,description,attributes,price,currency,availability,source_ref) VALUES(:id,:sku,:name,:category,:brand,:description,CAST(:attrs AS jsonb),:price,:currency,:availability,:source_ref)'),{**row,'attrs':json.dumps(row['attributes'],ensure_ascii=False)})
                for row in embeddings:conn.execute(text('INSERT INTO product_embeddings(id,product_id,model_name,source_text,embedding) VALUES(:id,:product_id,:model_name,:source_text,CAST(:embedding AS vector))'),row)
            engine.dispose()
            with tempfile.TemporaryDirectory(dir=folder) as storage:
                env={**os.environ,'DATABASE_URL':target,'AUTH_JWT_SECRET':uuid7().hex+uuid7().hex,'IMAGE_STORAGE_DIR':storage,'VISION_CHAT_RETRIEVAL':'text_catalog','VISION_TEST_IMAGE':str(image),'VISION_TEST_REPORT':str(report),'VISION_TEST_SCREENSHOT':str(folder/'mobile.png')}
                with (folder/'backend.log').open('w',encoding='utf-8') as log:
                    process=subprocess.Popen([sys.executable,'-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8001'],cwd=root/'backend',env=env,stdout=log,stderr=log,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                    try:
                        for _ in range(100):
                            try:
                                if httpx.get('http://127.0.0.1:8001/api/v1/health',timeout=1,trust_env=False).status_code==200:break
                            except httpx.HTTPError:pass
                            time.sleep(.1)
                        else:raise RuntimeError('Isolated backend not ready')
                        return subprocess.run([shutil.which('node.exe') or 'node',str(script)],cwd=root/'frontend',env=env,timeout=150).returncode
                    finally:
                        process.terminate();process.wait(timeout=10);process=None
        finally:
            if process:process.kill();process.wait()
            admin.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(name)))

if __name__=='__main__':raise SystemExit(main())
