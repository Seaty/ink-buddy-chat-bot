import { StrictMode } from "react";
import { afterEach, it, expect, vi } from "vitest";
import {
  render,
  screen,
  fireEvent,
  cleanup,
  waitFor,
} from "@testing-library/react";
import { AccountForm } from "../src/features/auth/account-form";
import { api } from "../src/lib/api";
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  window.history.replaceState(null, "", "/");
});
it("register checks confirmation and submits user details", async () => {
  const register = vi.spyOn(api, "register").mockResolvedValue({});
  render(<AccountForm mode="register" />);
  fireEvent.change(screen.getByLabelText("อีเมล"), {
    target: { value: "new@example.com" },
  });
  fireEvent.change(screen.getByLabelText("รหัสผ่าน", { exact: true }), {
    target: { value: "NewPassword123!" },
  });
  fireEvent.change(screen.getByLabelText("ยืนยันรหัสผ่าน"), {
    target: { value: "wrong confirmation" },
  });
  fireEvent.click(screen.getByRole("button", { name: "สมัครสมาชิก" }));
  expect(screen.getByRole("alert")).toHaveTextContent("ไม่ตรงกัน");
  expect(register).not.toHaveBeenCalled();
  fireEvent.change(screen.getByLabelText("ยืนยันรหัสผ่าน"), {
    target: { value: "NewPassword123!" },
  });
  fireEvent.click(screen.getByRole("button", { name: "สมัครสมาชิก" }));
  await waitFor(() =>
    expect(register).toHaveBeenCalledWith(
      "new@example.com",
      "NewPassword123!",
      null,
    ),
  );
  expect(await screen.findByRole("status")).toHaveTextContent("สมัครสำเร็จ");
});
it("forgot password displays the same generic success", async () => {
  vi.spyOn(api, "forgotPassword").mockResolvedValue({});
  render(<AccountForm mode="forgot" />);
  fireEvent.change(screen.getByLabelText("อีเมล"), {
    target: { value: "unknown@example.com" },
  });
  fireEvent.click(
    screen.getByRole("button", { name: "ส่งลิงก์รีเซ็ตรหัสผ่าน" }),
  );
  expect(await screen.findByRole("status")).toHaveTextContent(
    "หากอีเมลนี้มีบัญชี",
  );
});
it("reset reads fragment into memory, removes URL token and submits once", async () => {
  const token = "x".repeat(43);
  window.history.replaceState(null, "", "/reset-password#token=" + token);
  const reset = vi.spyOn(api, "resetPassword").mockResolvedValue();
  render(<StrictMode><AccountForm mode="reset" /></StrictMode>);
  await waitFor(() => expect(window.location.hash).toBe(""));
  fireEvent.change(screen.getByLabelText("รหัสผ่านใหม่", { exact: true }), {
    target: { value: "Replacement123!" },
  });
  fireEvent.change(screen.getByLabelText("ยืนยันรหัสผ่าน"), {
    target: { value: "Replacement123!" },
  });
  fireEvent.click(screen.getByRole("button", { name: "บันทึกรหัสผ่านใหม่" }));
  await waitFor(() =>
    expect(reset).toHaveBeenCalledWith(token, "Replacement123!"),
  );
  expect(await screen.findByRole("status")).toHaveTextContent(
    "เปลี่ยนรหัสผ่านแล้ว",
  );
});
it("reset without token offers a fresh link", () => {
  render(<StrictMode><AccountForm mode="reset" /></StrictMode>);
  expect(screen.getByRole("alert")).toHaveTextContent("ไม่พบ token");
  expect(screen.getByRole("link", { name: "ขอลิงก์ใหม่" })).toHaveAttribute(
    "href",
    "/forgot-password",
  );
});

it.each(["abcdefghij1!", "ABCDEFGHIJ1!", "Abcdefghijk!", "Abcdefghij12", "Abcdefghi1! ", "Abcdefghi1!\t", "A"+"b".repeat(22)+"1!"])("rejects invalid new password %s before API", async (password) => {
  const register = vi.spyOn(api, "register").mockResolvedValue({});
  render(<AccountForm mode="register" />);
  fireEvent.change(screen.getByLabelText("อีเมล"), {target:{value:"new@example.com"}});
  fireEvent.change(screen.getByLabelText("รหัสผ่าน", {exact:true}), {target:{value:password}});
  fireEvent.change(screen.getByLabelText("ยืนยันรหัสผ่าน"), {target:{value:password}});
  fireEvent.submit(screen.getByRole("button", {name:"สมัครสมาชิก"}).closest("form")!);
  expect(screen.getByRole("alert")).toHaveTextContent("12–24");
  expect(register).not.toHaveBeenCalled();
});
