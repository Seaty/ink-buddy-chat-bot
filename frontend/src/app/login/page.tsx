"use client";
import { useState, type FormEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "@/features/auth/provider";
import { errorText } from "@/lib/api";
export default function Login() {
  const auth = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await auth.login(email, password);
      setPassword("");
      router.push("/chat");
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <main className="login">
      <Link href="/chat">← กลับไปที่แชต</Link>
      <section className="card">
        <div className="brand-mark">ib</div>
        <h1>ยินดีต้อนรับกลับ</h1>
        <p className="muted">เข้าสู่ระบบเพื่อดูแลแชตของคุณใน Ink Buddy</p>
        <form onSubmit={submit} className="grid gap-4">
          <label>
            อีเมล
            <input
              type="email"
              autoComplete="username"
              required
              maxLength={320}
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </label>
          <label>
            รหัสผ่าน
            <input
              type="password"
              autoComplete="current-password"
              required
              maxLength={1024}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </label>
          {error && (
            <p role="alert" className="error">
              {error}
            </p>
          )}
          <button className="primary" disabled={busy || auth.loading}>
            {busy ? "กำลังเข้าสู่ระบบ…" : "เข้าสู่ระบบ"}
          </button>
        </form>
        <div className="flex justify-between gap-3 mt-4">
          <Link href="/register" className="button">
            สมัครสมาชิก
          </Link>
          <Link href="/forgot-password" className="button">
            ลืมรหัสผ่าน?
          </Link>
        </div>
        <p className="muted text-sm">หรือกลับไปใช้งานแบบ Guest ได้</p>
      </section>
    </main>
  );
}
