import { afterEach, describe, it, expect, vi } from "vitest";
import { ApiClient, ApiError } from "../src/lib/api";
const response = (status: number, data: unknown) =>
  new Response(status === 204 ? null : JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
afterEach(() => vi.restoreAllMocks());
describe("Auth client", () => {
  it("restores existing guest without creating a new one and deduplicates bootstrap", async () => {
    const fetch = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(response(401, {}))
      .mockResolvedValueOnce(response(200, { id: "guest" }));
    const client = new ApiClient("http://test");
    const [a, b] = await Promise.all([client.bootstrap(), client.bootstrap()]);
    expect(a).toEqual(b);
    expect(a.kind).toBe("guest");
    expect(fetch).toHaveBeenCalledTimes(2);
  });
  it("refreshes simultaneous GETs once and never falls back from a bad Bearer", async () => {
    let refreshes = 0;
    const fetch = vi
      .spyOn(globalThis, "fetch")
      .mockImplementation(async (url, options) => {
        const path = String(url);
        if (path.endsWith("/login"))
          return response(200, { access_token: "old" });
        if (path.endsWith("/users/me")) return response(200, { id: "u" });
        if (path.endsWith("/refresh")) {
          refreshes++;
          await new Promise((r) => setTimeout(r, 10));
          return response(200, { access_token: "new" });
        }
        return response(
          (options?.headers as Record<string, string>).Authorization ===
            "Bearer new"
            ? 200
            : 401,
          { items: [] },
        );
      });
    const client = new ApiClient("http://test");
    await client.login("a@b.com", "secret");
    await Promise.all([
      client.request("/chat-sessions"),
      client.request("/chat-sessions"),
    ]);
    expect(refreshes).toBe(1);
    expect(
      fetch.mock.calls.every(([, o]) => o?.credentials === "include"),
    ).toBe(true);
  });
  it("does not retry a mutation after refreshing", async () => {
    const fetch = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(response(200, { access_token: "old" }))
      .mockResolvedValueOnce(response(200, { id: "u" }))
      .mockResolvedValueOnce(response(401, {}))
      .mockResolvedValueOnce(response(200, { access_token: "new" }));
    const client = new ApiClient("http://test");
    await client.login("a@b.com", "secret");
    await expect(
      client.request("/chat-sessions", "POST", {}),
    ).rejects.toBeInstanceOf(ApiError);
    expect(
      fetch.mock.calls.filter(([p]) => String(p).endsWith("/chat-sessions")),
    ).toHaveLength(1);
  });
  it("surfaces a bootstrap outage instead of silently creating Guest", async () => {
    const fetch = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(response(500, {}));
    await expect(
      new ApiClient("http://test").bootstrap(),
    ).rejects.toBeInstanceOf(ApiError);
    expect(fetch).toHaveBeenCalledTimes(1);
  });
  it("notifies on expired Guest without automatic mutation retry", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(response(401, {}));
    const client = new ApiClient("http://test");
    const expired = vi.fn();
    client.onUnauthorized = expired;
    await expect(client.request("/chat-sessions")).rejects.toBeInstanceOf(
      ApiError,
    );
    expect(expired).toHaveBeenCalledOnce();
  });
});
