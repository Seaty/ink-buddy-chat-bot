"""Real HTTP/browser smoke using disposable PostgreSQL and the running frontend.
The browser forwards its API requests to this isolated server; responses are not mocked.
Run from backend: python -m scripts.test_chat_browser
"""

import os
import argparse
import shutil
import socket
import subprocess
import time
import json
from datetime import datetime, timezone
from pathlib import Path

import httpx
import psycopg
from app.core.identifiers import uuid7
from dotenv import dotenv_values
from psycopg import sql
from sqlalchemy.engine import URL

BROWSER = r"""
const {chromium}=require(require.resolve('@playwright/test',{paths:[process.cwd()]}));
const assert=require('node:assert/strict');
const fs=require('node:fs');
(async()=>{
const browser=await chromium.launch({channel:'msedge'});
const frontendUrl=process.env.INK_BUDDY_SMOKE_FRONTEND || 'http://localhost:3000';
const viewports=JSON.parse(process.env.INK_BUDDY_SMOKE_VIEWPORTS || '[{"name":"mobile","width":390,"height":844}]');
const results=[];
try {
 for(const viewport of viewports) {
 const page=await browser.newPage({viewport:{width:viewport.width,height:viewport.height}});
 page.setDefaultTimeout(70000);
 await page.route('http://localhost:8000/api/v1/**', async route=>{
  try {
   const response=await route.fetch({url:route.request().url().replace('localhost:8000','127.0.0.1:8001'),timeout:65000});
   await route.fulfill({response});
  } catch { await route.abort('timedout'); }
 });
 await page.goto(frontendUrl+'/chat');
 const draft=page.getByLabel('ร่างคำถามของคุณ');
 await draft.fill('ปากกาเจลไม่เกิน 100 บาท');
 const firstResponse=page.waitForResponse(r=>r.request().method()==='POST' && /\/chat-sessions\/[^/]+\/messages$/.test(new URL(r.url()).pathname));
 await draft.press('Enter');
 const sentResponse=await firstResponse;
 assert.equal(sentResponse.status(),201);
 const originalPair=await sentResponse.json();
 assert.equal(originalPair.user_message.role,'user');
 assert.equal(originalPair.assistant_message.role,'assistant');
 assert.equal(originalPair.assistant_message.product_refs.length,1);
 const replay=await page.evaluate(async ({url,body})=>{
   const response=await fetch(url,{method:'POST',credentials:'include',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
   return {status:response.status,data:await response.json()};
 },{url:sentResponse.url(),body:sentResponse.request().postDataJSON()});
 assert.equal(replay.status,201);
 assert.deepEqual(replay.data,originalPair);
 const history=await page.evaluate(async url=>(await fetch(url,{credentials:'include'})).json(),sentResponse.url());
 assert.equal(history.items.length,2);
 await page.getByText('Browser Smoke Pen',{exact:true}).waitFor();
 if(process.argv.includes('--rag')) await page.getByLabel('แหล่งคำตอบ').filter({hasText:/^AI$/}).first().waitFor();
 const chatUrl=page.url();
 await page.reload();
 await page.getByText('Browser Smoke Pen',{exact:true}).waitFor();
 await page.goto(frontendUrl+'/register');
 await page.getByLabel('อีเมล',{exact:true}).fill('smoke+'+viewport.name+'@example.com');
 await page.getByLabel('รหัสผ่าน',{exact:true}).fill('SmokePassword123!');
 await page.getByLabel('ยืนยันรหัสผ่าน').fill('SmokePassword123!');
 await page.getByRole('button',{name:'สมัครสมาชิก'}).click();
 await page.getByRole('status').waitFor();
 await page.goto(frontendUrl+'/login');
 await page.getByLabel('อีเมล',{exact:true}).fill('smoke+'+viewport.name+'@example.com');
 await page.getByLabel('รหัสผ่าน',{exact:true}).fill('SmokePassword123!');
 await page.getByRole('button',{name:'เข้าสู่ระบบ',exact:true}).click();
 await page.getByRole('button',{name:'ย้ายแชตเข้าบัญชี'}).click();
 await page.goto(chatUrl);
 await page.getByText('Browser Smoke Pen',{exact:true}).waitFor();
 await draft.fill('ปากกาเจลไม่เกิน 10 บาท');
 if(process.argv.includes('--rag')) {
  await draft.fill('ปากกาเจลไม่เกิน 100 บาท');
  await draft.press('Enter');
  await page.getByLabel('แหล่งคำตอบ').filter({hasText:/^AI$/}).nth(1).waitFor();
  await draft.fill('ปากกาเจลไม่เกิน 10 บาท');
 }
 await draft.press('Enter');
 await page.getByText(/ยังไม่พบสินค้าที่ตรงกับคำถามในข้อมูล catalog/).waitFor();
 if(process.argv.includes('--rag')) await page.getByLabel('แหล่งคำตอบ').filter({hasText:/กฎระบบ/}).first().waitFor();
 assert(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth),'horizontal overflow');
 if(process.env.INK_BUDDY_SMOKE_SCREENSHOT) await page.screenshot({path:process.env.INK_BUDDY_SMOKE_SCREENSHOT.replace('.png','-'+viewport.name+'.png'),fullPage:true});
 results.push({viewport,checks:['guest_send','product_refs','idempotent_replay','history_two_rows_after_replay','reload_history','register_login','guest_claim','user_send','no_match_policy_badge','no_horizontal_overflow']});
 await page.close();
 }
 if(process.env.INK_BUDDY_SMOKE_REPORT) fs.writeFileSync(process.env.INK_BUDDY_SMOKE_REPORT,JSON.stringify({
   status:'passed',tested_at:new Date().toISOString(),frontend_url:frontendUrl,results,
   mode:process.argv.includes('--rag')?'real_openrouter_rag':'catalog_template',
   api_transport:'browser route forwards to real isolated HTTP API; no response mocks',
   catalog:'synthetic fixture in disposable PostgreSQL; not production catalog',
 },null,2));
 console.log('Real browser -> HTTP API -> isolated PostgreSQL -> '+(process.argv.includes('--rag')?'OpenRouter RAG':'template')+': PASS (Guest/User/claim/history/no matches)');
} finally {await browser.close();}
})().catch(e=>{console.error(e.name+': browser acceptance failed; inspect local screenshot/API log without dumping request headers');process.exitCode=1});
"""

BROWSER_CONVERSATION = r"""
const {chromium}=require(require.resolve('@playwright/test',{paths:[process.cwd()]}));
const assert=require('node:assert/strict');const fs=require('node:fs');
(async()=>{
 const browser=await chromium.launch({channel:'msedge'});const results=[];
 try{for(const viewport of JSON.parse(process.env.INK_BUDDY_SMOKE_VIEWPORTS)){
  const page=await browser.newPage({viewport:{width:viewport.width,height:viewport.height}});
  await page.route('http://localhost:8000/api/v1/**',async route=>{
   try {
    const response=await route.fetch({url:route.request().url().replace('localhost:8000','127.0.0.1:8001'),timeout:65000});
    await route.fulfill({response});
   } catch { await route.abort('timedout'); }
  });
  await page.goto(process.env.INK_BUDDY_SMOKE_FRONTEND+'/chat');
  const draft=page.getByLabel('ร่างคำถามของคุณ');
  async function send(question){
   await draft.fill(question);
   const pending=page.waitForResponse(r=>r.request().method()==='POST'&&/\/chat-sessions\/[^/]+\/messages$/.test(new URL(r.url()).pathname),{timeout:70000});
   await draft.press('Enter');const response=await pending;
   assert.equal(response.status(),201);return {response,pair:await response.json()};
  }
  const first=await send('ปากกาหมึกน้ำเงิน สามรุ่นถูกที่สุด และมีสีอื่นไหม');
  const refs=first.pair.assistant_message.product_refs;
  assert.deepEqual(refs.map(r=>Number(r.price)),[50,60,70]);
  assert(refs.every(r=>r.ink_color==='น้ำเงิน'));
  assert.equal(refs[1].variants.length,1);assert.equal(refs[1].variants[0].ink_color,'แดง');
  await page.getByLabel('สีอื่นของรุ่นเดียวกัน').waitFor();
  await page.getByRole('link',{name:'แหล่งข้อมูลราคา',exact:true}).first().waitFor();
  const replay=await page.evaluate(async ({url,body})=>{
   const r=await fetch(url,{method:'POST',credentials:'include',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
   return {status:r.status,pair:await r.json()};
  },{url:first.response.url(),body:first.response.request().postDataJSON()});
  assert.equal(replay.status,201);assert.deepEqual(replay.pair,first.pair);
  const second=await send('ตัวที่สองราคาเท่าไร');
  assert.equal(second.pair.assistant_message.product_refs[0].id,refs[1].id);
  assert.equal(Number(second.pair.assistant_message.product_refs[0].price),60);
  const policy=await send('ปากกาหมึกน้ำเงิน ไม่เกิน 1 บาท');
  assert.equal(policy.pair.assistant_message.model_name,'catalog_policy');
  await page.getByLabel('แหล่งคำตอบ').filter({hasText:/กฎระบบ/}).waitFor();
  const chatUrl=page.url();await page.reload();
  await page.getByLabel('สีอื่นของรุ่นเดียวกัน').waitFor();
  const history=await page.evaluate(async url=>(await fetch(url,{credentials:'include'})).json(),first.response.url());
  assert.equal(history.items.length,6);
  assert.equal(history.items[1].product_refs[1].variants[0].id,refs[1].variants[0].id);
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  await page.screenshot({path:process.env.INK_BUDDY_SMOKE_SCREENSHOT.replace('.png','-'+viewport.name+'.png'),fullPage:true});
  results.push({viewport,checks:['three_ranked_blue_products','exclude_null_pack_and_purple','same_family_red_variant','separate_price_source','ordinal_followup','replay','six_history_rows','policy_no_match','reload_nested_references','no_horizontal_overflow']});
  await page.close();
 }}finally{await browser.close();}
 fs.writeFileSync(process.env.INK_BUDDY_SMOKE_REPORT,JSON.stringify({status:'passed',tested_at:new Date().toISOString(),frontend_url:process.env.INK_BUDDY_SMOKE_FRONTEND,mode:'real_openrouter_conversational_rag',api_transport:'forwarded real HTTP; no response mocks',catalog:'synthetic disposable PostgreSQL',results},null,2));
 console.log('Conversational RAG real browser acceptance: PASS');
})().catch(error=>{console.error(error.name+': conversational acceptance failed; inspect local screenshot/API log without dumping request headers');process.exitCode=1});
"""


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--rag',action='store_true')
    parser.add_argument('--conversation',action='store_true',help='Real RAG price/context/variant browser acceptance')
    parser.add_argument('--frontend-url',choices=('http://localhost:3000','http://localhost:3002'),default='http://localhost:3000')
    parser.add_argument('--viewports',choices=('mobile','all'),default='mobile')
    args=parser.parse_args()
    if args.conversation:args.rag=True
    with socket.socket() as probe:
        try:
            probe.bind(("127.0.0.1", 8001))
        except OSError:
            raise RuntimeError(
                "Port8001 already in use; isolated browser test needs a free port"
            ) from None
    repo = Path(__file__).resolve().parents[2]
    cfg = dotenv_values(repo / "docker/.env")
    name = "ink_buddy_test_" + uuid7().hex
    connection = dict(
        host="127.0.0.1",
        port=int(cfg.get("POSTGRES_PORT") or 5432),
        user=cfg["POSTGRES_USER"],
        password=cfg["POSTGRES_PASSWORD"],
        dbname=cfg["POSTGRES_DB"],
    )
    process = None
    folder = repo / ".local/browser-smoke"
    folder.mkdir(parents=True, exist_ok=True)
    script = folder / "smoke.cjs"
    script.write_text(BROWSER_CONVERSATION if args.conversation else BROWSER, encoding="utf-8")
    with psycopg.connect(**connection, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        try:
            connection["dbname"] = name
            with psycopg.connect(**connection, autocommit=True) as db:
                db.execute(
                    (repo / "database/ddl/001_init.sql").read_text(encoding="utf-8")
                )
                db.execute(
                    "INSERT INTO products(name,category,brand,price,currency,source_ref) VALUES('Browser Smoke Pen','gel_pen','Smoke',50,'THB','https://example.test/smoke')"
                )
                if args.conversation:
                    db.execute('DELETE FROM products')
                    for product_name,price,family,unit in [
                        ('ปากกาเจล รุ่น S1 หมึกสีน้ำเงิน',50,'S1','ด้าม'),
                        ('ปากกาเจล รุ่น S2 หมึกสีน้ำเงิน',60,'S2','ด้าม'),
                        ('ปากกาเจล รุ่น S3 หมึกสีน้ำเงิน',70,'S3','ด้าม'),
                        ('ปากกาเจล รุ่น S2 หมึกสีแดง',60,'S2','ด้าม'),
                        ('ปากกาเจล รุ่น S4 หมึกสีม่วง',1,'S4','ด้าม'),
                        ('ปากกาเจล รุ่น S5 หมึกสีน้ำเงิน',None,'S5','ด้าม'),
                        ('ปากกาเจล รุ่น S6 หมึกสีน้ำเงิน แพ็ค 12',5,'S6','แพ็ค 12 ด้าม')]:
                        db.execute("INSERT INTO products(name,category,brand,price,currency,source_ref,attributes) VALUES(%s,'gel_pen','Smoke',%s,'THB','https://example.test/catalog',%s::jsonb)",
                            (product_name,price,json.dumps({'model_family':family,'price_selling_unit':unit,'price_source_ref':'https://example.test/price','price_tax_basis':'excludes_vat','price_tax_basis_verification':'user_assumed_for_coursework_not_verified'})))
            env = os.environ.copy()
            env.update(
                CHAT_ADAPTER='openrouter_catalog' if args.rag else 'catalog_template',
                DATABASE_URL=URL.create(
                    "postgresql+psycopg",
                    username=connection["user"],
                    password=connection["password"],
                    host=connection["host"],
                    port=connection["port"],
                    database=name,
                ).render_as_string(hide_password=False),
                AUTH_JWT_SECRET=uuid7().hex + uuid7().hex,
                APP_ENVIRONMENT="development",
                CORS_ORIGINS=json.dumps([args.frontend_url]),
                INK_BUDDY_SMOKE_REPORT=str(repo/'docs/report/RAG_BROWSER_ACCEPTANCE.json'),
                INK_BUDDY_SMOKE_SCREENSHOT=str(folder/'acceptance-mobile.png'),
            )
            if args.conversation:
                env['INK_BUDDY_SMOKE_REPORT']=str(repo/'docs/report/RAG_CONVERSATION_BROWSER.json')
                env['INK_BUDDY_SMOKE_SCREENSHOT']=str(folder/'conversation.png')
            if args.rag:
                from app.core.config import Settings
                from app.services.product.text_index import TextIndexService
                from app.schemas.admin import TextIndexRequest
                from sqlalchemy import create_engine
                engine=create_engine(env['DATABASE_URL'])
                try:
                    indexed=TextIndexService(engine,Settings(database_url=env['DATABASE_URL'])).index(TextIndexRequest(limit=7 if args.conversation else 1))
                    if indexed.indexed!=(7 if args.conversation else 1):raise RuntimeError('Real smoke indexing failed')
                finally:engine.dispose()
            import sys

            with (folder / "backend.log").open("w", encoding="utf-8") as log:
                process = subprocess.Popen(
                    [
                        sys.executable,
                        "-m",
                        "uvicorn",
                        "app.main:app",
                        "--host",
                        "127.0.0.1",
                        "--port",
                        "8001",
                    ],
                    cwd=repo / "backend",
                    env=env,
                    stdout=log,
                    stderr=log,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                for _ in range(100):
                    if process.poll() is not None:
                        raise RuntimeError(
                            "Isolated backend failed to start; see .local/browser-smoke/backend.log"
                        )
                    try:
                        if (
                            httpx.get(
                                "http://127.0.0.1:8001/api/v1/health",
                                timeout=1,
                                trust_env=False,
                            ).status_code
                            == 200
                        ):
                            break
                    except httpx.HTTPError:
                        pass
                    time.sleep(0.1)
                else:
                    raise RuntimeError("Isolated backend startup timed out")
                result = subprocess.run(
                    [
                        shutil.which("node.exe") or shutil.which("node"),
                        str(script),
                    ] + (['--rag'] if args.rag else []),
                    cwd=repo / "frontend",
                    env={**os.environ,
                         'INK_BUDDY_SMOKE_REPORT':env['INK_BUDDY_SMOKE_REPORT'],
                         'INK_BUDDY_SMOKE_SCREENSHOT':env['INK_BUDDY_SMOKE_SCREENSHOT'],
                         'INK_BUDDY_SMOKE_FRONTEND':args.frontend_url,
                         'INK_BUDDY_SMOKE_VIEWPORTS':json.dumps([{'name':'mobile','width':390,'height':844}]+([
                             {'name':'tablet','width':820,'height':1180},{'name':'desktop','width':1440,'height':900}] if args.viewports=='all' else []))},
                    timeout=420 if args.viewports=='all' else 180,
                )
                if result.returncode:
                    Path(env['INK_BUDDY_SMOKE_REPORT']).write_text(json.dumps({
                        'status':'failed','tested_at':datetime.now(timezone.utc).isoformat(),
                        'exit_code':result.returncode,'mode':'real_openrouter_rag' if args.rag else 'catalog_template'
                    },indent=2),encoding='utf-8')
                return result.returncode
        finally:
            if process:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            admin.execute(
                sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name))
            )


if __name__ == "__main__":
    raise SystemExit(main())
