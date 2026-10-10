"use client";
import { useEffect, useRef, useState, type FormEvent } from "react";
import Link from "next/link";
import { api, errorText } from "@/lib/api";
export function AccountForm({
  mode,
}: {
  mode: "register" | "forgot" | "reset";
}) {
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [token, setToken] = useState("");
  const [ready, setReady] = useState(mode !== "reset");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState(false);
  const tokenRead = useRef(false);
  useEffect(() => {
    if (mode === "reset" && !tokenRead.current) {
      tokenRead.current = true;
      const hash = new URLSearchParams(window.location.hash.slice(1));
      setToken(hash.get("token") || "");
      window.history.replaceState(null, "", window.location.pathname);
      setReady(true);
    }
  }, [mode]);
  const titles = {
    register: "สร้างบัญชี Ink Buddy",
    forgot: "ลืมรหัสผ่าน?",
    reset: "ตั้งรหัสผ่านใหม่",
  };
  async function submit(e: FormEvent) {
    e.preventDefault();
    setError("");
    if (mode !== "forgot" && password !== confirm) {
      setError("รหัสผ่านทั้งสองช่องไม่ตรงกัน");
      return;
    }
    if (mode !== "forgot" && (password.length < 12 || password.length > 24 || /[\s\u0085\u001c-\u001f]/u.test(password) || !/[a-z]/.test(password) || !/[A-Z]/.test(password) || !/[0-9]/.test(password) || !/[!-/:-@[-`{-~]/.test(password))) {
      setError("รหัสผ่านต้องยาว 12–24 ตัว มี a–z, A–Z, 0–9 และอักขระพิเศษ เช่น !@# โดยไม่มีช่องว่าง");
      return;
    }
    setBusy(true);
    try {
      if (mode === "register")
        await api.register(email, password, name.trim() || null);
      else if (mode === "forgot") await api.forgotPassword(email);
      else await api.resetPassword(token, password);
      setSuccess(true);
      setPassword("");
      setConfirm("");
      setToken("");
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <main className="login">
      <Link href="/login">← กลับเข้าสู่ระบบ</Link>
      <section className="card">
        <div className="brand-mark">ib</div>
        <h1>{titles[mode]}</h1>
        {success ? (
          <section role="status">
            <p>
              {mode === "register"
                ? "สมัครสำเร็จแล้ว คุณสามารถเข้าสู่ระบบได้ทันที"
                : mode === "forgot"
                  ? "หากอีเมลนี้มีบัญชีที่ใช้งานได้ ระบบจะส่งลิงก์ให้ กรุณาตรวจกล่องจดหมาย ลิงก์ใช้งานได้ 15 นาที"
                  : "เปลี่ยนรหัสผ่านแล้ว กรุณาเข้าสู่ระบบใหม่ อุปกรณ์ที่เคยเข้าสู่ระบบถูกออกจากระบบแล้ว"}
            </p>
            <Link href="/login" className="button primary">
              ไปหน้าเข้าสู่ระบบ
            </Link>
            {mode === "forgot" && (
              <button onClick={() => setSuccess(false)}>ขอลิงก์อีกครั้ง</button>
            )}
          </section>
        ) : (
          <>
            {mode === "reset" && ready && !token ? (
              <p role="alert" className="error">
                ไม่พบ token กรุณาเปิดลิงก์จากอีเมล หรือ{" "}
                <Link href="/forgot-password">ขอลิงก์ใหม่</Link>
              </p>
            ) : (
              <form onSubmit={submit} className="grid gap-4">
                {mode === "register" && (
                  <label>
                    ชื่อที่แสดง (ไม่บังคับ)
                    <input
                      autoComplete="nickname"
                      maxLength={120}
                      value={name}
                      onChange={(e) => setName(e.target.value)}
                    />
                  </label>
                )}
                {mode !== "reset" && (
                  <label>
                    อีเมล
                    <input
                      required
                      type="email"
                      autoComplete="email"
                      maxLength={320}
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                    />
                  </label>
                )}
                {mode !== "forgot" && (
                  <>
                    <p className="muted text-sm">
                      รหัสผ่าน 12–24 ตัว ต้องมี a–z, A–Z, 0–9 และอักขระพิเศษ เช่น !@# ไม่มีช่องว่าง
                    </p>
                    <label>
                      {mode === "reset" ? "รหัสผ่านใหม่" : "รหัสผ่าน"}
                      <input
                        required
                        type="password"
                        autoComplete="new-password"
                        minLength={12}
                        maxLength={24}
                        value={password}
                        onChange={(e) => setPassword(e.target.value)}
                      />
                    </label>
                    <label>
                      ยืนยันรหัสผ่าน
                      <input
                        required
                        type="password"
                        autoComplete="new-password"
                        minLength={12}
                        maxLength={24}
                        value={confirm}
                        onChange={(e) => setConfirm(e.target.value)}
                      />
                    </label>
                  </>
                )}
                {error && (
                  <p className="error" role="alert">
                    {error}
                  </p>
                )}
                <button className="primary" disabled={busy || !ready}>
                  {busy
                    ? "กำลังดำเนินการ…"
                    : mode === "register"
                      ? "สมัครสมาชิก"
                      : mode === "forgot"
                        ? "ส่งลิงก์รีเซ็ตรหัสผ่าน"
                        : "บันทึกรหัสผ่านใหม่"}
                </button>
              </form>
            )}
            {mode === "reset" && error && (
              <Link href="/forgot-password" className="button">
                ขอลิงก์ใหม่
              </Link>
            )}
          </>
        )}
      </section>
    </main>
  );
}
