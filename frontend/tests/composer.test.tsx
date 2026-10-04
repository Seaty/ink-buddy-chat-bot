import { afterEach, it, expect, vi } from "vitest";
import { render, screen, fireEvent, cleanup } from "@testing-library/react";
import { useState } from "react";
import { Composer } from "../src/features/chat/composer";
vi.mock("@/features/auth/provider", () => ({
  useAuth: () => {
    const [drafts, setDrafts] = useState<Record<string, string>>({});
    return {
      drafts,
      setDraft: (k: string, v: string) => setDrafts((d) => ({ ...d, [k]: v })),
    };
  },
}));
afterEach(cleanup);
HTMLDialogElement.prototype.showModal = function () {
  this.setAttribute("open", "");
};
HTMLDialogElement.prototype.close = function () {
  this.removeAttribute("open");
};
it("prompt fills editable draft without sending or creating a chat", () => {
  const fetch = vi.spyOn(globalThis, "fetch");
  render(<Composer draftKey="home" showPrompts />);
  fireEvent.click(screen.getByRole("button", { name: /เลือกปากกา/ }));
  const textarea = screen.getByLabelText("ร่างคำถามของคุณ");
  expect(textarea).toHaveValue(
    "ช่วยแนะนำปากกาสำหรับจดโน้ตทุกวัน พร้อมอธิบายวิธีเลือก",
  );
  expect(textarea).toHaveFocus();
  fireEvent.change(textarea, { target: { value: "my draft" } });
  expect(textarea).toHaveValue("my draft");
  fireEvent.keyDown(textarea, { key: "Enter" });
  expect(screen.getByRole("button", { name: "ส่งข้อความ" })).toBeDisabled();
  expect(fetch).not.toHaveBeenCalled();
  fetch.mockRestore();
});
it("asks before replacing existing draft and can clear it", () => {
  render(<Composer draftKey="home" showPrompts />);
  const textarea = screen.getByLabelText("ร่างคำถามของคุณ");
  fireEvent.change(textarea, { target: { value: "original" } });
  fireEvent.click(screen.getByRole("button", { name: /เลือกสมุด/ }));
  expect(screen.getByRole("dialog")).toBeInTheDocument();
  expect(textarea).toHaveValue("original");
  fireEvent.click(screen.getByRole("button", { name: "เก็บร่างเดิม" }));
  expect(textarea).toHaveValue("original");
  fireEvent.click(screen.getByRole("button", { name: /เลือกสมุด/ }));
  fireEvent.click(screen.getByRole("button", { name: "แทนที่ร่าง" }));
  expect(textarea).toHaveValue("สมุดแบบไหนเหมาะกับการจดเลกเชอร์และใช้ไฮไลต์?");
  fireEvent.click(screen.getByRole("button", { name: "ล้างร่าง" }));
  expect(textarea).toHaveValue("");
  expect(textarea).toHaveAttribute("maxlength", "4000");
});
