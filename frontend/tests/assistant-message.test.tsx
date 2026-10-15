import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  answerWords,
  AssistantMessage,
  beginAnswerReveal,
  ThinkingIndicator,
} from "../src/features/chat/assistant-message";
import type { Message } from "../src/lib/types";

const reply = (id: string): Message => ({
  id,
  session_id: "chat",
  sequence_number: 2,
  role: "assistant",
  content: "ลองดูปากกาสีน้ำเงิน รุ่นนี้ราคา 50 บาทครับ",
  image_id: null,
  product_refs: [
    {
      id: "pen",
      name: "ปากกาแนะนำ",
      sku: null,
      price: "50",
      currency: "THB",
      availability: null,
      source_ref: null,
    },
  ],
});
beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date("2026-10-15"));
  vi.stubGlobal("matchMedia", () => ({
    matches: false,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  }));
});
afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});
describe("assistant presentation", () => {
  it("segments Thai words without changing text, punctuation or newlines", () => {
    const content = "ปากกาน้ำเงิน\nราคา 50 บาท — รุ่น BL77";
    expect(answerWords(content).join("")).toBe(content);
    expect(answerWords("ปากกาน้ำเงิน").length).toBeGreaterThan(1);
  });
  it("reveals new replies gradually and displays references only after completion", () => {
    const message = reply("new-reply");
    beginAnswerReveal(message.id);
    const { container } = render(<AssistantMessage message={message} />);
    expect(container.querySelector("[data-revealing='true']")).toBeTruthy();
    expect(screen.queryByLabelText("สินค้าที่เกี่ยวข้อง")).toBeNull();
    act(() => {
      vi.advanceTimersByTime(120);
    });
    expect(
      container.querySelector(".answer-text")!.textContent!.length,
    ).toBeGreaterThan(0);
    expect(
      container.querySelector(".answer-text")!.textContent!.length,
    ).toBeLessThan(message.content.length);
    act(() => {
      vi.advanceTimersByTime(2000);
    });
    expect(screen.getByText(message.content)).toBeTruthy();
    expect(screen.getByLabelText("สินค้าที่เกี่ยวข้อง")).toBeTruthy();
  });
  it("shows historical messages instantly and lets readers skip the reveal", () => {
    render(<AssistantMessage message={reply("old-reply")} />);
    expect(screen.queryByText("แสดงคำตอบทั้งหมด")).toBeNull();
    cleanup();
    const message = reply("skip-reply");
    beginAnswerReveal(message.id);
    render(<AssistantMessage message={message} />);
    fireEvent.click(screen.getByText("แสดงคำตอบทั้งหมด"));
    act(() => {
      vi.advanceTimersByTime(100);
    });
    expect(screen.getByLabelText("สินค้าที่เกี่ยวข้อง")).toBeTruthy();
  });
  it("respects reduced motion and exposes one accessible loading status", () => {
    vi.stubGlobal("matchMedia", () => ({
      matches: true,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }));
    const message = reply("reduced-reply");
    beginAnswerReveal(message.id);
    render(<AssistantMessage message={message} />);
    expect(screen.queryByText("แสดงคำตอบทั้งหมด")).toBeNull();
    cleanup();
    render(<ThinkingIndicator />);
    expect(screen.getByRole("status").textContent).toContain(
      "กำลังค้นข้อมูลและเตรียมคำตอบ",
    );
  });
});
