import type { Guest, Profile, Identity } from "./types";

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
  ) {
    super(message);
  }
}
export class ApiClient {
  private token: string | null = null;
  private refreshFlight: Promise<void> | null = null;
  private bootstrapFlight: Promise<Identity> | null = null;
  onUnauthorized: (() => void) | null = null;
  constructor(
    private base = process.env.NEXT_PUBLIC_API_BASE_URL ||
      "http://localhost:8000/api/v1",
  ) {}
  private async raw<T>(
    path: string,
    method = "GET",
    body?: unknown,
    bearer = true,
  ): Promise<T> {
    const headers: Record<string, string> = {};
    if (body !== undefined) headers["Content-Type"] = "application/json";
    if (bearer && this.token) headers.Authorization = `Bearer ${this.token}`;
    const response = await fetch(this.base + path, {
      method,
      headers,
      credentials: "include",
      cache: "no-store",
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      throw new ApiError(
        response.status,
        data.error?.code || "REQUEST_FAILED",
        data.error?.message || "ไม่สามารถดำเนินการได้",
      );
    }
    return response.status === 204 ? (undefined as T) : response.json();
  }
  async refresh(): Promise<void> {
    if (!this.refreshFlight) {
      this.refreshFlight = this.raw<{ access_token: string }>(
        "/auth/refresh",
        "POST",
        undefined,
        false,
      )
        .then((result) => {
          this.token = result.access_token;
        })
        .catch((error) => {
          if (error instanceof ApiError && error.status === 401)
            this.token = null;
          throw error;
        })
        .finally(() => {
          this.refreshFlight = null;
        });
    }
    return this.refreshFlight;
  }
  async request<T>(path: string, method = "GET", body?: unknown): Promise<T> {
    const snapshot = this.token;
    try {
      return await this.raw<T>(path, method, body);
    } catch (error) {
      if (!(error instanceof ApiError) || error.status !== 401) throw error;
      if (snapshot) {
        try {
          if (this.token === snapshot) await this.refresh();
        } catch (refreshError) {
          if (refreshError instanceof ApiError && refreshError.status === 401)
            this.onUnauthorized?.();
          throw refreshError;
        }
        if (method === "GET")
          return this.raw<T>(path).catch((e) => {
            if (e instanceof ApiError && e.status === 401)
              this.onUnauthorized?.();
            throw e;
          });
      } else {
        this.onUnauthorized?.();
      }
      throw error; // Never automatically retry mutations.
    }
  }
  bootstrap(): Promise<Identity> {
    if (!this.bootstrapFlight)
      this.bootstrapFlight = this.restore().finally(() => {
        this.bootstrapFlight = null;
      });
    return this.bootstrapFlight;
  }
  private async restore(): Promise<Identity> {
    try {
      await this.refresh();
      return { kind: "user", profile: await this.raw<Profile>("/users/me") };
    } catch (e) {
      if (!(e instanceof ApiError) || e.status !== 401) throw e;
      this.token = null;
    }
    try {
      return { kind: "guest", guest: await this.currentGuest() };
    } catch (e) {
      if (!(e instanceof ApiError) || e.status !== 401) throw e;
    }
    return { kind: "guest", guest: await this.createGuest() };
  }
  currentGuest() {
    return this.raw<Guest>(
      "/auth/guest-sessions/current",
      "GET",
      undefined,
      false,
    );
  }
  createGuest() {
    return this.raw<Guest>("/auth/guest-sessions", "POST", undefined, false);
  }
  async login(email: string, password: string) {
    const result = await this.raw<{ access_token: string }>(
      "/auth/login",
      "POST",
      { email, password },
      false,
    );
    this.token = result.access_token;
    return this.raw<Profile>("/users/me");
  }
  async logout() {
    try {
      await this.raw<void>("/auth/logout", "POST", undefined, false);
    } catch (e) {
      if (!(e instanceof ApiError) || e.status !== 401) throw e;
    }
    this.token = null;
  }
  register(email: string, password: string, display_name: string | null) {
    return this.raw(
      "/auth/register",
      "POST",
      { email, password, display_name },
      false,
    );
  }
  forgotPassword(email: string) {
    return this.raw("/auth/forgot-password", "POST", { email }, false);
  }
  async resetPassword(token: string, password: string) {
    await this.raw("/auth/reset-password", "POST", { token, password }, false);
    if (this.token) {
      this.token = null;
      this.onUnauthorized?.();
    }
  }
  claim() {
    return this.raw("/auth/guest-sessions/current/claim", "POST");
  }
}
export const api = new ApiClient();
export function errorText(error: unknown) {
  if (error instanceof ApiError) {
    if (error.code === "EMAIL_ALREADY_REGISTERED")
      return "อีเมลนี้สมัครไว้แล้ว กรุณาเข้าสู่ระบบหรือลืมรหัสผ่าน";
    if (error.code === "INVALID_RESET_TOKEN")
      return "ลิงก์นี้หมดอายุหรือใช้แล้ว กรุณาขอลิงก์ใหม่";
    if (error.status === 401)
      return "สิทธิ์ใช้งานหมดอายุ กรุณาลองใหม่หรือเข้าสู่ระบบ";
    if (error.status === 404) return "ไม่พบแชตนี้ หรือคุณไม่มีสิทธิ์เข้าถึง";
    if (error.status === 429)
      return "ใช้งานถี่เกินไป กรุณารอสักครู่แล้วลองใหม่";
    if (error.status === 422) return "ข้อมูลไม่ถูกต้อง กรุณาตรวจสอบอีกครั้ง";
    return "ไม่สามารถดำเนินการได้ กรุณาลองใหม่";
  }
  return "เชื่อมต่อระบบไม่ได้ กรุณาตรวจสอบการเชื่อมต่อแล้วลองใหม่";
}
