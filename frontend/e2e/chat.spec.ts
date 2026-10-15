import { test, expect, type Page } from "@playwright/test";
import type { ProductReference } from "../src/lib/types";

async function fixture(
  page: Page,
  failMessageOnce = false,
  options: {
    content?: string;
    delayMs?: number;
    products?: ProductReference[];
  } = {},
) {
  let loggedIn = false;
  let claimed = false;
  let sequence = 0;
  let posts = 0;
  type Chat = {
    id: string;
    title: string;
    summary: null;
    created_at: string;
    updated_at: string;
    owner: string;
  };
  const chats: Chat[] = [];
  const histories: Record<string, any[]> = {};
  const sentIds: string[] = [];
  const guest = {
    id: "018f1234-0000-7000-8000-000000000001",
    expires_at: "2099-01-01T00:00:00Z",
    image_uploads_remaining: 3,
  };
  const profile = {
    id: "018f1234-0000-7000-8000-000000000002",
    email: "user@example.com",
    display_name: "ผู้ใช้ทดสอบ",
    role: "user",
  };
  await page.route("http://localhost:8000/api/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname.replace("/api/v1", "");
    const method = request.method();
    const owner = request.headers().authorization ? "user" : "guest";
    const send = (data: unknown, status = 200) =>
      route.fulfill({
        status,
        contentType: "application/json",
        body: status === 204 ? undefined : JSON.stringify(data),
      });
    const fail = (status: number) =>
      send({ error: { code: "UNAUTHORIZED", message: "failed" } }, status);
    if (method === "OPTIONS") return send({});
    if (path === "/auth/register") return send({ message: "Created" }, 201);
    if (path === "/auth/forgot-password")
      return send({ message: "If eligible" }, 202);
    if (path === "/auth/reset-password") return send({ message: "Changed" });
    if (path === "/auth/refresh")
      return loggedIn ? send({ access_token: "test-user" }) : fail(401);
    if (path === "/auth/guest-sessions/current")
      return claimed ? fail(401) : send(guest);
    if (path === "/auth/guest-sessions") {
      claimed = false;
      return send(guest, 201);
    }
    if (path === "/auth/login") {
      loggedIn = true;
      return send({ access_token: "test-user" });
    }
    if (path === "/auth/logout") {
      loggedIn = false;
      return send(null, 204);
    }
    if (path === "/users/me") return loggedIn ? send(profile) : fail(401);
    if (path === "/auth/guest-sessions/current/claim") {
      claimed = true;
      for (const c of chats) if (c.owner === "guest") c.owner = "user";
      return send({ chat_sessions_claimed: chats.length });
    }
    if (path === "/chat-sessions") {
      if (method === "POST") {
        posts++;
        const c = {
          id: `018f1234-0000-7000-8000-${String(++sequence).padStart(12, "0")}`,
          title: "แชตใหม่",
          summary: null,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
          owner,
        };
        chats.unshift(c);
        return send(c, 201);
      }
      return send({
        items: chats.filter((c) => c.owner === owner),
        next_cursor: null,
      });
    }
    const sid = path.split("/")[2];
    const c = chats.find((c) => c.id === sid && c.owner === owner);
    if (!c) return fail(404);
    if (path.endsWith("/messages")) {
      if (method === "POST") {
        const body = request.postDataJSON();
        sentIds.push(body.client_request_id);
        if (options.delayMs)
          await new Promise((resolve) => setTimeout(resolve, options.delayMs));
        if (failMessageOnce) {
          failMessageOnce = false;
          return fail(503);
        }
        const history = (histories[sid] ||= []);
        const user = {
          id: `message-${history.length + 1}`,
          session_id: sid,
          sequence_number: history.length + 1,
          role: "user",
          content: body.content,
          image_id: null,
          product_refs: null,
        };
        const assistant = {
          ...user,
          id: `message-${history.length + 2}`,
          sequence_number: history.length + 2,
          role: "assistant",
          content: options.content || "พบสินค้าจาก catalog",
          product_refs: options.products || [
            {
              id: "product-1",
              sku: "PEN",
              name: "ปากกาเจลทดสอบ",
              price: "50.00",
              currency: "THB",
              availability: null,
              source_ref: "https://example.test/product",
            },
          ],
        };
        history.push(user, assistant);
        return send({ user_message: user, assistant_message: assistant }, 201);
      }
      return send({ items: histories[sid] || [], next_cursor: null });
    }
    if (method === "PATCH") {
      c.title = request.postDataJSON().title;
      return send(c);
    }
    if (method === "DELETE") {
      chats.splice(chats.indexOf(c), 1);
      return send(null, 204);
    }
    return send(c);
  });
  return { posts: () => posts, sentIds: () => sentIds };
}
async function openList(page: Page) {
  if (await page.getByRole("button", { name: "☰ แชตของคุณ" }).isVisible())
    await page.getByRole("button", { name: "☰ แชตของคุณ" }).click();
}

test("session lifecycle, drafts, prompt confirmation, direct link and mobile navigation", async ({
  page,
}, info) => {
  const mock = await fixture(page);
  await page.goto("/chat");
  await expect(
    page.getByRole("heading", { name: "วันนี้อยากรู้เรื่องเครื่องเขียนอะไร?" }),
  ).toBeVisible();
  await page.getByRole("button", { name: /เลือกปากกา/ }).click();
  const draft = page.getByLabel("ร่างคำถามของคุณ");
  await expect(draft).toBeFocused();
  await expect(draft).toHaveValue(/ช่วยแนะนำปากกา/);
  expect(mock.posts()).toBe(0);
  await page.getByRole("button", { name: /เลือกสมุด/ }).click();
  await expect(
    page.getByRole("dialog", { name: "แทนที่ร่างเดิม?" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "เก็บร่างเดิม" }).click();
  await expect(draft).toHaveValue(/ช่วยแนะนำปากกา/);
  await openList(page);
  await page.getByRole("button", { name: "＋ สร้างแชตใหม่" }).click();
  await expect(page).toHaveURL(/\/chat\/[\w-]+$/);
  await expect(page.getByRole("heading", { name: "แชตใหม่" })).toBeVisible();
  const path = new URL(page.url()).pathname;
  await draft.fill("ร่างของแชตนี้");
  await openList(page);
  await page.locator('a[href="/chat"]:visible').first().click();
  await expect(page).toHaveURL(/\/chat$/);
  await expect(draft).toHaveValue(/ช่วยแนะนำปากกา/);
  await openList(page);
  await page
    .getByRole("navigation", { name: "รายการแชต" })
    .getByRole("link", { name: /แชตใหม่/ })
    .click();
  await expect(draft).toHaveValue("ร่างของแชตนี้");
  await page.getByRole("button", { name: "เปลี่ยนชื่อ", exact: true }).click();
  await page.getByLabel("ชื่อแชต", { exact: true }).fill("สมุดที่สนใจ");
  await page.getByRole("button", { name: "บันทึกชื่อ" }).click();
  await expect(
    page.getByRole("heading", { name: "สมุดที่สนใจ" }),
  ).toBeVisible();
  await page.goto(path);
  await expect(
    page.getByRole("heading", { name: "สมุดที่สนใจ" }),
  ).toBeVisible();
  await expect(draft).toHaveValue("");
  await expect(page.getByRole("button", { name: "ส่งข้อความ" })).toBeDisabled();
  await page.screenshot({
    path: `test-results/chat-${info.project.name}.png`,
    fullPage: true,
  });
  await page.getByRole("button", { name: "ลบแชต", exact: true }).click();
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "ลบแชต", exact: true })
    .click();
  await expect(page).toHaveURL(/\/chat$/);
  await expect(
    page.getByRole("heading", { name: "วันนี้อยากรู้เรื่องเครื่องเขียนอะไร?" }),
  ).toBeVisible();
});

test("login offers claim, transfers list and logout clears draft", async ({
  page,
}) => {
  await fixture(page);
  await page.goto("/chat");
  await expect(
    page.getByRole("heading", { name: "วันนี้อยากรู้เรื่องเครื่องเขียนอะไร?" }),
  ).toBeVisible();
  await openList(page);
  await page.getByRole("button", { name: "＋ สร้างแชตใหม่" }).click();
  await expect(page).toHaveURL(/\/chat\/[\w-]+$/);
  await page.goto("/login");
  await page.getByLabel("อีเมล", { exact: true }).fill("user@example.com");
  await page.getByLabel("รหัสผ่าน", { exact: true }).fill("password123");
  await page.getByRole("button", { name: "เข้าสู่ระบบ", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "ย้ายแชตเข้าบัญชี" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "ย้ายแชตเข้าบัญชี" }).click();
  await expect(
    page.getByRole("button", { name: "ย้ายแชตเข้าบัญชี" }),
  ).toHaveCount(0);
  await page.getByLabel("ร่างคำถามของคุณ").fill("private draft");
  await openList(page);
  await expect(
    page
      .getByRole("navigation", { name: "รายการแชต" })
      .getByRole("link", { name: /แชตใหม่/ }),
  ).toBeVisible();
  await page.getByRole("button", { name: "ออกจากระบบ" }).click();
  await expect(
    page.getByRole("heading", { name: "วันนี้อยากรู้เรื่องเครื่องเขียนอะไร?" }),
  ).toBeVisible();
  await expect(page.getByLabel("ร่างคำถามของคุณ")).toHaveValue("");
});

test("register and password recovery screens", async ({ page }) => {
  await fixture(page);
  await page.goto("/register");
  await page.getByLabel("อีเมล", { exact: true }).fill("new@example.com");
  await page.getByLabel("รหัสผ่าน", { exact: true }).fill("ValidPassword123!");
  await page.getByLabel("ยืนยันรหัสผ่าน").fill("ValidPassword123!");
  await page.getByRole("button", { name: "สมัครสมาชิก" }).click();
  await expect(page.getByRole("status")).toContainText("สมัครสำเร็จ");
  await page.getByRole("link", { name: "ไปหน้าเข้าสู่ระบบ" }).click();
  await page.getByRole("link", { name: "ลืมรหัสผ่าน?" }).click();
  await expect(page).toHaveURL(/\/forgot-password$/);
  await page.getByLabel("อีเมล", { exact: true }).fill("new@example.com");
  await page.getByRole("button", { name: "ส่งลิงก์รีเซ็ตรหัสผ่าน" }).click();
  await expect(page.getByRole("status")).toContainText("หากอีเมลนี้มีบัญชี");
  await page.goto("/reset-password#token=" + "x".repeat(43));
  await expect(page).toHaveURL(/\/reset-password$/);
  await page
    .getByLabel("รหัสผ่านใหม่", { exact: true })
    .fill("Replacement123!");
  await page.getByLabel("ยืนยันรหัสผ่าน").fill("Replacement123!");
  await page.getByRole("button", { name: "บันทึกรหัสผ่านใหม่" }).click();
  await expect(page.getByRole("status")).toContainText("เปลี่ยนรหัสผ่านแล้ว");
});

test("send from home persists answer and references after reload", async ({
  page,
}) => {
  const state = await fixture(page);
  await page.goto("/chat");
  const draft = page.getByLabel("ร่างคำถามของคุณ");
  await draft.fill("ปากกาเจลไม่เกิน 100 บาท");
  await draft.press("Enter");
  await expect(page).toHaveURL(/\/chat\/[\w-]+$/);
  await expect(
    page.getByText("พบสินค้าจาก catalog", { exact: true }),
  ).toBeVisible();
  await expect(page.getByText("ปากกาเจลทดสอบ", { exact: true })).toBeVisible();
  await expect(draft).toHaveValue("");
  expect(state.posts()).toBe(1);
  expect(state.sentIds()[0]).toMatch(
    /^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/,
  );
  await page.reload();
  await expect(
    page.getByText("พบสินค้าจาก catalog", { exact: true }),
  ).toBeVisible();
});

test("failed first send retains draft, request ID and created chat for retry", async ({
  page,
}) => {
  const state = await fixture(page, true);
  await page.goto("/chat");
  const draft = page.getByLabel("ร่างคำถามของคุณ");
  await draft.fill("ปากกาเจล");
  await page.getByRole("button", { name: "ส่งข้อความ", exact: true }).click();
  await expect(page).toHaveURL(/\/chat\/[\w-]+$/);
  await expect(draft).toHaveValue("ปากกาเจล");
  await expect(
    page.getByRole("alert").filter({ hasText: "ไม่สามารถดำเนินการ" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "ส่งข้อความ", exact: true }).click();
  await expect(
    page.getByText("พบสินค้าจาก catalog", { exact: true }),
  ).toBeVisible();
  expect(state.posts()).toBe(1);
  expect(state.sentIds()[0]).toBe(state.sentIds()[1]);
});

test("pending animation, word reveal, follow scroll and reading older text", async ({
  page,
}, info) => {
  const content = Array.from(
    { length: 120 },
    (_, i) =>
      `ตัวเลือกที่ ${i + 1} ปากกาหมึกน้ำเงินราคา 50 บาท เหมาะสำหรับจดโน้ต`,
  ).join("\n");
  const state = await fixture(page, false, { content, delayMs: 600 });
  await page.goto("/chat");
  await page.getByLabel("ร่างคำถามของคุณ").fill("แนะนำปากกาหน่อย");
  await page.getByRole("button", { name: "ส่งข้อความ", exact: true }).click();
  await expect(page.getByLabel("กำลังรอคำตอบ")).toBeVisible();
  await expect(
    page.getByText("กำลังค้นข้อมูลและเตรียมคำตอบ", { exact: true }),
  ).toBeVisible();
  await expect(page.locator("[data-revealing='true']")).toBeVisible();
  await expect(page.getByLabel("กำลังรอคำตอบ")).toHaveCount(0);
  await expect
    .poll(() => page.evaluate(() => window.scrollY), { timeout: 6000 })
    .toBeGreaterThan(300);
  await page.mouse.wheel(0, -1200);
  await expect(
    page.getByRole("button", { name: "กลับไปข้อความล่าสุด" }),
  ).toBeVisible();
  const before = await page.evaluate(() => ({
    y: scrollY,
    height: document.documentElement.scrollHeight,
  }));
  await expect
    .poll(() => page.evaluate(() => document.documentElement.scrollHeight))
    .toBeGreaterThan(before.height + 80);
  expect(
    Math.abs((await page.evaluate(() => scrollY)) - before.y),
  ).toBeLessThan(80);
  await page.getByRole("button", { name: "กลับไปข้อความล่าสุด" }).click();
  await expect(
    page.getByRole("button", { name: "กลับไปข้อความล่าสุด" }),
  ).toHaveCount(0);
  await page.getByRole("button", { name: "แสดงคำตอบทั้งหมด" }).click();
  await expect(page.getByLabel("สินค้าที่เกี่ยวข้อง")).toBeVisible();
  await expect
    .poll(() =>
      page.evaluate(
        () => document.documentElement.scrollHeight - innerHeight - scrollY,
      ),
    )
    .toBeLessThan(120);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  expect(state.posts()).toBe(1);
  await page.screenshot({
    path: `../.local/chat-ui-${info.project.name}.png`,
    fullPage: true,
  });
  await page.reload();
  await expect(page.getByLabel("สินค้าที่เกี่ยวข้อง")).toBeVisible();
  await expect(page.locator("[data-revealing='true']")).toHaveCount(0);
});

test("reduced motion displays the answer immediately", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await fixture(page);
  await page.goto("/chat");
  await page.getByLabel("ร่างคำถามของคุณ").fill("ปากกาเจล");
  await page.getByRole("button", { name: "ส่งข้อความ", exact: true }).click();
  await expect(page.getByLabel("สินค้าที่เกี่ยวข้อง")).toBeVisible();
  await expect(page.locator("[data-revealing='true']")).toHaveCount(0);
});

test("product cards keep variants, sources and details visually separate", async ({
  page,
}, info) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  const pen = {
    id: "blue",
    sku: "BL77-BLUE",
    name: "Pentel Energel BL77 หมึกสีน้ำเงิน",
    price: "50.00",
    currency: "THB",
    availability: null,
    source_ref: "https://example.test/catalog",
    price_source_ref: "https://example.test/price",
    ink_color: "น้ำเงิน",
    selling_unit: "ด้าม",
    price_basis: "excludes_vat",
    price_verification: "user_assumed_for_coursework_not_verified",
  };
  await fixture(page, false, {
    content:
      "ลองดูสองรุ่นนี้ครับ\n• Pentel Energel BL77 — 50 บาท / ด้าม\n• Pentel Feel-it — 10 บาท / ด้าม\nBL77 มีสีแดงให้เลือกด้วยครับ",
    products: [
      {
        ...pen,
        variants: [
          {
            ...pen,
            id: "red",
            name: "Pentel Energel BL77 หมึกสีแดง",
            ink_color: "แดง",
          },
        ],
      },
      {
        ...pen,
        id: "feel-it",
        name: "Pentel Feel-it หมึกน้ำเงิน ด้ามสีส้ม",
        price: "10.00",
        body_color: "ส้ม",
        variants: [],
      },
    ],
  });
  await page.goto("/chat");
  await page
    .getByLabel("ร่างคำถามของคุณ")
    .fill("ปากกาหมึกน้ำเงิน มีสีอื่นด้วยไหม");
  await page.getByRole("button", { name: "ส่งข้อความ", exact: true }).click();
  await expect(page).toHaveURL(/\/chat\/[\w-]+$/);
  await expect(page.getByLabel("สีอื่นของรุ่นเดียวกัน")).toBeVisible();
  await page.locator(".product-collection").scrollIntoViewIfNeeded();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await expect(page.getByRole("link", { name: "แหล่งข้อมูลราคา" })).toHaveCount(
    3,
  );
  await page.locator(".product-details summary").first().click();
  await expect(
    page.getByText("ฐานภาษีเป็นสมมติฐานสำหรับส่งงาน").first(),
  ).toBeVisible();
  await page.screenshot({
    path: `../.local/chat-cards-${info.project.name}.png`,
    fullPage: true,
  });
});
