"use client";
import { useRef, useState } from "react";
import { useAuth } from "@/features/auth/provider";
import { suggestedPrompts } from "./prompts";
import { Dialog } from "@/components/ui/dialog";
export function Composer({
  draftKey,
  showPrompts,
  onSend,
  busy = false,
}: {
  draftKey: string;
  showPrompts: boolean;
  onSend?: () => void;
  busy?: boolean;
}) {
  const { drafts, setDraft } = useAuth();
  const text = drafts[draftKey] || "";
  const ref = useRef<HTMLTextAreaElement>(null);
  const [replacement, setReplacement] = useState<string | null>(null);
  function apply(value: string) {
    setDraft(draftKey, value);
    setReplacement(null);
    ref.current?.focus();
    setTimeout(() => ref.current?.focus(), 0);
  }
  return (
    <>
      {showPrompts && (
        <section aria-label="คำถามแนะนำ" className="prompt-grid">
          {suggestedPrompts
            .filter((p) => p.enabled)
            .map((p) => (
              <button
                key={p.id}
                className="prompt"
                disabled={busy}
                onClick={() =>
                  text && text !== p.text
                    ? setReplacement(p.text)
                    : apply(p.text)
                }
              >
                <strong>{p.label}</strong>
                <span>{p.text}</span>
                <span aria-hidden="true">↗</span>
              </button>
            ))}
        </section>
      )}
      <section className="composer" aria-label="ร่างข้อความ">
        <label htmlFor="draft">ร่างคำถามของคุณ</label>
        <textarea
          ref={ref}
          id="draft"
          placeholder="ลองเลือกคำถามแนะนำ หรือพิมพ์คำถามของคุณ…"
          value={text}
          disabled={busy}
          maxLength={4000}
          rows={3}
          onChange={(e) => setDraft(draftKey, e.target.value)}
          onKeyDown={(e) => {
            if (
              e.key === "Enter" &&
              !e.shiftKey &&
              !e.nativeEvent.isComposing &&
              e.keyCode !== 229
            ) {
              e.preventDefault();
              if (!busy && text.trim() && onSend) onSend();
            }
          }}
          aria-describedby="draft-help"
        />
        <div className="flex items-center justify-between gap-3">
          <button onClick={() => apply("")} disabled={!text || busy}>
            ล้างร่าง
          </button>
          <div className="flex items-center gap-3">
            {text.length >= 3500 && (
              <span aria-live="polite">
                {text.length.toLocaleString()} / 4,000
              </span>
            )}
            <button
              className="primary"
              disabled={busy || !text.trim() || !onSend}
              onClick={onSend}
            >
              ส่งข้อความ
            </button>
          </div>
        </div>
        <p id="draft-help" className="muted text-sm">
          Enter เพื่อส่ง · Shift+Enter เพื่อขึ้นบรรทัดใหม่
        </p>
      </section>
      {replacement !== null && (
        <Dialog title="แทนที่ร่างเดิม?" onClose={() => setReplacement(null)}>
          <p>คุณมีข้อความที่ร่างไว้ ต้องการใช้คำถามแนะนำแทนหรือไม่?</p>
          <div className="actions">
            <button onClick={() => setReplacement(null)}>เก็บร่างเดิม</button>
            <button className="primary" onClick={() => apply(replacement)}>
              แทนที่ร่าง
            </button>
          </div>
        </Dialog>
      )}
    </>
  );
}
