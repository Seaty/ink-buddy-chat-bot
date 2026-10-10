"use client";
import { useEffect, useRef, useState, type FormEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "@/features/auth/provider";
import { api, errorText } from "@/lib/api";
import type { ChatSession, Message, Page } from "@/lib/types";
import { Dialog } from "@/components/ui/dialog";
import { Composer } from "./composer";

type Edit = { kind: "rename" | "delete"; chat: ChatSession };
function unique<T extends { id: string }>(items: T[]) {
  return Array.from(new Map(items.map((item) => [item.id, item])).values());
}
export function ChatWorkspace({ sessionId }: { sessionId?: string }) {
  const auth = useAuth();
  const router = useRouter();
  const [list, setList] = useState<Page<ChatSession>>({
    items: [],
    next_cursor: null,
  });
  const [chat, setChat] = useState<ChatSession | null>(null);
  const [messages, setMessages] = useState<Page<Message>>({
    items: [],
    next_cursor: null,
  });
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [listError, setListError] = useState("");
  const [detailError, setDetailError] = useState("");
  const [actionError, setActionError] = useState("");
  const [busy, setBusy] = useState(false);
  const [drawer, setDrawer] = useState(false);
  const [edit, setEdit] = useState<Edit | null>(null);
  const [title, setTitle] = useState("");
  const [version, setVersion] = useState(0);
  const [claimBusy, setClaimBusy] = useState(false);
  const scope = useRef("");
  scope.current = `${auth.revision}:${sessionId || "home"}`;
  useEffect(() => {
    let active = true;
    setList({ items: [], next_cursor: null });
    setListError("");
    setActionError("");
    if (!auth.identity) {
      setLoading(false);
      return;
    }
    setLoading(true);
    api
      .request<Page<ChatSession>>("/chat-sessions")
      .then((data) => {
        if (active) setList(data);
      })
      .catch((e) => {
        if (active) setListError(errorText(e));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [auth.identity, auth.revision, version]);
  useEffect(() => {
    let active = true;
    setChat(null);
    setMessages({ items: [], next_cursor: null });
    setDetailError("");
    setEdit(null);
    setDrawer(false);
    if (!sessionId || !auth.identity) {
      setDetailLoading(false);
      return;
    }
    setDetailLoading(true);
    Promise.all([
      api.request<ChatSession>(`/chat-sessions/${sessionId}`),
      api.request<Page<Message>>(`/chat-sessions/${sessionId}/messages`),
    ])
      .then(([c, m]) => {
        if (active) {
          setChat(c);
          setMessages(m);
        }
      })
      .catch((e) => {
        if (active) setDetailError(errorText(e));
      })
      .finally(() => {
        if (active) setDetailLoading(false);
      });
    return () => {
      active = false;
    };
  }, [sessionId, auth.identity, auth.revision, version]);
  async function create() {
    setBusy(true);
    setActionError("");
    const snapshot = scope.current;
    try {
      const created = await api.request<ChatSession>(
        "/chat-sessions",
        "POST",
        {},
      );
      if (scope.current === snapshot) {
        setVersion((v) => v + 1);
        router.push(`/chat/${created.id}`);
      }
    } catch (e) {
      setActionError(errorText(e));
    } finally {
      setBusy(false);
    }
  }
  async function loadMore() {
    setBusy(true);
    const snapshot = scope.current;
    try {
      const page = await api.request<Page<ChatSession>>(
        `/chat-sessions?cursor=${encodeURIComponent(list.next_cursor!)}`,
      );
      if (snapshot === scope.current)
        setList((previous) => ({
          items: unique([...previous.items, ...page.items]),
          next_cursor: page.next_cursor,
        }));
    } catch (e) {
      setListError(errorText(e));
    } finally {
      setBusy(false);
    }
  }
  async function older() {
    setBusy(true);
    const snapshot = scope.current;
    try {
      const page = await api.request<Page<Message>>(
        `/chat-sessions/${sessionId}/messages?cursor=${encodeURIComponent(messages.next_cursor!)}`,
      );
      if (snapshot === scope.current)
        setMessages((previous) => ({
          items: unique([...page.items, ...previous.items]).sort(
            (a, b) => a.sequence_number - b.sequence_number,
          ),
          next_cursor: page.next_cursor,
        }));
    } catch (e) {
      setActionError(errorText(e));
    } finally {
      setBusy(false);
    }
  }
  async function save(e: FormEvent) {
    e.preventDefault();
    if (!edit) return;
    setBusy(true);
    setActionError("");
    const snapshot = scope.current;
    try {
      await api.request(
        `/chat-sessions/${edit.chat.id}`,
        edit.kind === "rename" ? "PATCH" : "DELETE",
        edit.kind === "rename" ? { title: title.trim() } : undefined,
      );
      if (snapshot === scope.current) {
        if (edit.kind === "delete") {
          auth.setDraft(edit.chat.id, "");
          if (sessionId === edit.chat.id) router.push("/chat");
        }
        setEdit(null);
        setVersion((v) => v + 1);
      }
    } catch (e) {
      setActionError(errorText(e));
    } finally {
      setBusy(false);
    }
  }
  async function logout() {
    setBusy(true);
    try {
      await auth.logout();
      router.push("/chat");
    } catch (e) {
      setActionError(errorText(e));
    } finally {
      setBusy(false);
    }
  }
  async function claim() {
    setClaimBusy(true);
    try {
      await auth.claim();
      router.push("/chat");
    } catch (e) {
      setActionError(errorText(e));
    } finally {
      setClaimBusy(false);
    }
  }
  function selectEdit(kind: "rename" | "delete", c: ChatSession) {
    setEdit({ kind, chat: c });
    setTitle(c.title || "");
    setActionError("");
  }
  const listPanel = (
    <>
      <div className="flex items-center justify-between gap-3">
        <Link href="/chat" className="brand">
          <span className="brand-mark">ib</span> Ink Buddy
        </Link>
        <button
          className="tablet-toggle"
          aria-label="ปิดรายการแชต"
          onClick={() => setDrawer(false)}
        >
          ✕
        </button>
      </div>
      <p className="eyebrow">พื้นที่เครื่องเขียนของคุณ</p>
      <button
        className="primary w-full"
        onClick={create}
        disabled={busy || !auth.identity}
      >
        ＋ สร้างแชตใหม่
      </button>
      <div className="flex items-center justify-between mt-6">
        <h2>แชตของคุณ</h2>
        <span className="muted text-sm">{list.items.length}</span>
      </div>
      {loading ? (
        <p role="status">กำลังโหลดแชต…</p>
      ) : (
        <nav aria-label="รายการแชต" className="chat-list">
          {list.items.map((c) => (
            <div
              key={c.id}
              className={`chat-row ${sessionId === c.id ? "selected" : ""}`}
            >
              <Link href={`/chat/${c.id}`} onClick={() => setDrawer(false)}>
                <span>{c.title || "แชตใหม่"}</span>
                <small>
                  {new Date(c.updated_at).toLocaleDateString("th-TH", {
                    day: "numeric",
                    month: "short",
                  })}
                </small>
              </Link>
              <button
                aria-label={`เปลี่ยนชื่อ ${c.title}`}
                onClick={() => selectEdit("rename", c)}
                disabled={busy}
              >
                ✎
              </button>
              <button
                aria-label={`ลบ ${c.title}`}
                onClick={() => selectEdit("delete", c)}
                disabled={busy}
              >
                ×
              </button>
            </div>
          ))}
        </nav>
      )}
      {!loading && !list.items.length && !listError && (
        <p className="muted">ยังไม่มีแชต เริ่มสร้างแชตแรกได้เลย</p>
      )}
      {listError && (
        <div role="alert" className="error">
          {listError}
          <button onClick={() => setVersion((v) => v + 1)}>ลองโหลดใหม่</button>
        </div>
      )}
      {list.next_cursor && (
        <button onClick={loadMore} disabled={busy}>
          โหลดแชตเพิ่มเติม
        </button>
      )}
      <footer className="account">
        <span>
          {auth.identity?.kind === "user"
            ? auth.identity.profile.display_name || auth.identity.profile.email
            : "ใช้งานแบบ Guest"}
        </span>
        {auth.identity?.kind === "guest" && (
          <small className="muted">
            โควตารูปเหลือ {auth.identity.guest.image_uploads_remaining} / 3
          </small>
        )}
        {auth.identity?.kind === "user" ? (
          <button onClick={logout} disabled={busy}>
            ออกจากระบบ
          </button>
        ) : (
          <Link href="/login" className="button">
            เข้าสู่ระบบ
          </Link>
        )}
      </footer>
    </>
  );
  if (auth.loading)
    return (
      <main className="center" role="status">
        กำลังเตรียมพื้นที่แชต…
      </main>
    );
  if (!auth.identity)
    return (
      <main className="center">
        <section className="card">
          <h1>
            {auth.expired ? "สิทธิ์ใช้งานหมดอายุ" : "เชื่อมต่อ Ink Buddy"}
          </h1>
          <p role="alert">
            {auth.expired
              ? "Guest เดิมที่หมดอายุไม่สามารถเปิดได้อีก คุณสามารถเริ่มรอบใหม่หรือเข้าสู่ระบบได้"
              : auth.error}
          </p>
          <button className="primary" onClick={() => auth.recover()}>
            ลองใหม่ / เริ่มใช้งาน
          </button>
          <Link href="/login" className="button">
            เข้าสู่ระบบ
          </Link>
        </section>
      </main>
    );
  return (
    <div className={`workspace ${sessionId ? "has-session" : ""}`}>
      <aside className="sidebar">{listPanel}</aside>
      {drawer && (
        <Dialog title="แชตของคุณ" onClose={() => setDrawer(false)}>
          <div className="drawer-panel">{listPanel}</div>
        </Dialog>
      )}
      <main className="conversation">
        <header className="topbar">
          <Link href="/chat" className="mobile-back">
            ← แชตทั้งหมด
          </Link>
          <button className="tablet-toggle" onClick={() => setDrawer(true)}>
            ☰ แชตของคุณ
          </button>
          <span className="muted text-sm">
            {auth.identity.kind === "user"
              ? "บัญชีของคุณ"
              : "Guest · ทดลองใช้งาน"}
          </span>
          {chat && (
            <div className="flex gap-2">
              <button
                onClick={() => selectEdit("rename", chat)}
                disabled={busy}
              >
                เปลี่ยนชื่อ
              </button>
              <button
                onClick={() => selectEdit("delete", chat)}
                disabled={busy}
              >
                ลบแชต
              </button>
            </div>
          )}
        </header>
        {auth.pendingGuest && (
          <section className="claim-banner">
            <div>
              <strong>เก็บแชต Guest ไว้ในบัญชี?</strong>
              <p>ย้ายแชตและรูปของ Guest รอบนี้เข้าบัญชีของคุณ</p>
            </div>
            <div className="actions">
              <button onClick={() => auth.dismissClaim()} disabled={claimBusy}>
                ใช้งานบัญชีก่อน
              </button>
              <button className="primary" onClick={claim} disabled={claimBusy}>
                {claimBusy ? "กำลังย้าย…" : "ย้ายแชตเข้าบัญชี"}
              </button>
            </div>
          </section>
        )}
        <div className="conversation-body">
          {actionError && !edit && (
            <p role="alert" className="error">
              {actionError}
            </p>
          )}
          {detailLoading ? (
            <p role="status">กำลังเปิดแชต…</p>
          ) : detailError ? (
            <section className="card">
              <p role="alert">{detailError}</p>
              <button onClick={() => setVersion((v) => v + 1)}>ลองใหม่</button>
              <Link href="/chat" className="button">
                กลับรายการแชต
              </Link>
            </section>
          ) : (
            <>
              {!messages.items.length ? (
                <section className="welcome">
                  <span className="welcome-icon">✎</span>
                  <p className="eyebrow">เพื่อนช่วยเลือกเครื่องเขียน</p>
                  <h1>
                    {chat?.title || "วันนี้อยากรู้เรื่องเครื่องเขียนอะไร?"}
                  </h1>
                  <p className="muted">
                    เริ่มจากคำถามแนะนำ หรือร่างคำถามในแบบของคุณ
                  </p>
                  {!sessionId && (
                    <button
                      onClick={create}
                      disabled={busy}
                      className="start-chat"
                    >
                      สร้างแชตเพื่อเก็บไว้เป็นหมวดหมู่ →
                    </button>
                  )}
                </section>
              ) : (
                <section aria-label="ประวัติข้อความ" className="messages">
                  {messages.next_cursor && (
                    <button onClick={older} disabled={busy}>
                      โหลดข้อความเก่ากว่า
                    </button>
                  )}
                  {messages.items.map((m) => (
                    <article key={m.id} className={`message ${m.role}`}>
                      <small>{m.role === "user" ? "คุณ" : "Ink Buddy"}</small>
                      <p>{m.content}</p>
                      {m.image_id && (
                        <p className="muted text-sm">มีรูปภาพแนบในข้อความนี้</p>
                      )}
                    </article>
                  ))}
                </section>
              )}
              <Composer
                key={sessionId || "home"}
                draftKey={sessionId || "home"}
                showPrompts={!messages.items.length}
              />
            </>
          )}
        </div>
        <footer className="conversation-footer">
          Ink Buddy · ถาม เลือก และค้นหาเครื่องเขียน
        </footer>
      </main>
      {edit && (
        <Dialog
          title={edit.kind === "rename" ? "เปลี่ยนชื่อแชต" : "ลบแชตนี้?"}
          onClose={() => {
            if (!busy) setEdit(null);
          }}
        >
          <form onSubmit={save}>
            {edit.kind === "rename" ? (
              <label>
                ชื่อแชต
                <input
                  autoFocus
                  required
                  maxLength={200}
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                />
              </label>
            ) : (
              <p>
                แชต “{edit.chat.title}” จะไม่แสดงในรายการ การลบไม่คืนโควตารูป
                Guest
              </p>
            )}
            {actionError && (
              <p className="error" role="alert">
                {actionError}
              </p>
            )}
            <div className="actions">
              <button
                type="button"
                onClick={() => setEdit(null)}
                disabled={busy}
              >
                ยกเลิก
              </button>
              <button
                className={edit.kind === "delete" ? "danger" : "primary"}
                disabled={busy || (edit.kind === "rename" && !title.trim())}
              >
                {busy
                  ? "กำลังบันทึก…"
                  : edit.kind === "rename"
                    ? "บันทึกชื่อ"
                    : "ลบแชต"}
              </button>
            </div>
          </form>
        </Dialog>
      )}
    </div>
  );
}
