"use client";
import { useEffect, useMemo, useState } from "react";
import type { Message } from "@/lib/types";
import { ProductReferenceCard } from "./product-reference";

// Only new replies animate. IDs/timestamps survive the home -> session route
// transition; no conversation text is cached outside React or persisted.
const reveals = new Map<string, number>();
export function beginAnswerReveal(id: string) {
  if (reveals.size >= 100) reveals.delete(reveals.keys().next().value!);
  reveals.set(id, Date.now());
}
export function answerWords(text: string) {
  return Array.from(
    new Intl.Segmenter("th", { granularity: "word" }).segment(text),
    (s) => s.segment,
  );
}

export function AssistantMessage({ message }: { message: Message }) {
  const words = useMemo(() => answerWords(message.content), [message.content]);
  const [started] = useState(() => reveals.get(message.id));
  const [visible, setVisible] = useState(started ? 0 : words.length);
  const complete = visible >= words.length;
  useEffect(() => {
    if (!started || complete) return;
    const motion = window.matchMedia("(prefers-reduced-motion: reduce)");
    let timer: ReturnType<typeof setInterval> | undefined;
    const finish = () => {
      setVisible(words.length);
      reveals.delete(message.id);
      if (timer) clearInterval(timer);
    };
    const update = () => {
      if (motion.matches) {
        finish();
        return;
      }
      const count = Math.min(
        words.length,
        Math.max(1, Math.floor((Date.now() - started) / 28)) *
          Math.max(1, Math.ceil(words.length / 300)),
      );
      setVisible(count);
      if (count >= words.length) finish();
    };
    update();
    timer = setInterval(update, 28);
    motion.addEventListener("change", update);
    return () => {
      clearInterval(timer);
      motion.removeEventListener("change", update);
    };
  }, [message.id, started, words.length, complete]);
  return (
    <div
      className="assistant-content"
      data-revealing={!complete}
      aria-live="polite"
    >
      {!complete && (
        <p className="sr-only" role="status">
          ได้รับคำตอบแล้ว กำลังแสดงข้อความ
        </p>
      )}
      <p className="answer-text" aria-hidden={!complete || undefined}>
        {words.slice(0, visible).join("")}
        {!complete && <span className="typing-cursor" aria-hidden="true" />}
      </p>
      {!complete && (
        <button
          className="reveal-all"
          onClick={() => {
            setVisible(words.length);
            reveals.delete(message.id);
          }}
        >
          แสดงคำตอบทั้งหมด
        </button>
      )}
      {complete && Boolean(message.product_refs?.length) && (
        <section
          className="product-collection"
          aria-label="สินค้าที่เกี่ยวข้อง"
        >
          <div className="product-collection-heading">
            <span>สินค้าที่เกี่ยวข้อง</span>
            <span>{message.product_refs!.length} รายการ</span>
          </div>
          <div className="product-grid">
            {message.product_refs!.map((p, index) => (
              <ProductReferenceCard
                key={p.id}
                product={p}
                position={index + 1}
              />
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

export function ThinkingIndicator() {
  return (
    <div className="thinking" role="status">
      <span className="thinking-orbit" aria-hidden="true">
        ✦
      </span>
      <div>
        <strong>กำลังค้นข้อมูลและเตรียมคำตอบ</strong>
        <span className="thinking-caption">
          Ink Buddy กำลังช่วยเลือกให้คุณ
          <span className="thinking-dots" aria-hidden="true">
            <i />
            <i />
            <i />
          </span>
        </span>
      </div>
    </div>
  );
}
