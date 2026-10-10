"""Real HTTP/browser smoke using disposable PostgreSQL and the running frontend.
The browser forwards its API requests to this isolated server; responses are not mocked.
Run from backend: python -m scripts.test_chat_browser
"""

import os
import shutil
import socket
import subprocess
import time
from pathlib import Path

import httpx
import psycopg
from app.core.identifiers import uuid7
from dotenv import dotenv_values
from psycopg import sql
from sqlalchemy.engine import URL

BROWSER = r"""
const {chromium}=require(require.resolve('@playwright/test',{paths:[process.cwd()]}));
(async()=>{
const browser=await chromium.launch({channel:'msedge'});
try {
 const page=await browser.newPage();
 await page.route('http://localhost:8000/api/v1/**', async route=>{
  const response=await route.fetch({url:route.request().url().replace('localhost:8000','127.0.0.1:8001')});
  await route.fulfill({response});
 });
 await page.goto('http://localhost:3000/chat');
 const draft=page.getByLabel('ร่างคำถามของคุณ');
 await draft.fill('ปากกาเจลไม่เกิน 100 บาท');
 await draft.press('Enter');
 await page.getByText('Browser Smoke Pen',{exact:true}).waitFor();
 const chatUrl=page.url();
 await page.reload();
 await page.getByText('Browser Smoke Pen',{exact:true}).waitFor();
 await page.goto('http://localhost:3000/register');
 await page.getByLabel('อีเมล',{exact:true}).fill('smoke@example.com');
 await page.getByLabel('รหัสผ่าน',{exact:true}).fill('SmokePassword123!');
 await page.getByLabel('ยืนยันรหัสผ่าน').fill('SmokePassword123!');
 await page.getByRole('button',{name:'สมัครสมาชิก'}).click();
 await page.getByRole('status').waitFor();
 await page.goto('http://localhost:3000/login');
 await page.getByLabel('อีเมล',{exact:true}).fill('smoke@example.com');
 await page.getByLabel('รหัสผ่าน',{exact:true}).fill('SmokePassword123!');
 await page.getByRole('button',{name:'เข้าสู่ระบบ',exact:true}).click();
 await page.getByRole('button',{name:'ย้ายแชตเข้าบัญชี'}).click();
 await page.goto(chatUrl);
 await page.getByText('Browser Smoke Pen',{exact:true}).waitFor();
 await draft.fill('ปากกาเจลไม่เกิน 10 บาท');
 await draft.press('Enter');
 await page.getByText(/ยังไม่พบสินค้าที่ตรงกับคำถามในข้อมูล catalog/).waitFor();
 console.log('Real browser -> HTTP API -> isolated PostgreSQL -> template: PASS (Guest/User/claim/history/no matches)');
} finally {await browser.close();}
})().catch(e=>{console.error(e.message);process.exitCode=1});
"""


def main():
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
    script.write_text(BROWSER, encoding="utf-8")
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
            env = os.environ.copy()
            env.update(
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
                CORS_ORIGINS='["http://localhost:3000"]',
            )
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
                        shutil.which("pnpm.cmd") or shutil.which("pnpm"),
                        "exec",
                        "node",
                        str(script),
                    ],
                    cwd=repo / "frontend",
                    timeout=120,
                )
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
