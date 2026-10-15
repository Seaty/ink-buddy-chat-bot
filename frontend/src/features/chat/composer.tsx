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
  const { drafts, setDraft, attachments, setAttachment, identity } = useAuth();
  const attachment = attachments?.[draftKey];
  const input = useRef<HTMLInputElement>(null);
  const [imageError, setImageError] = useState("");
  const remaining =
    identity?.kind === "guest" ? identity.guest.image_uploads_remaining : null;
  const quotaReached = remaining === 0;
  const maxChars = attachment ? 500 : 4000;
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
        <input
          ref={input}
          hidden
          tabIndex={-1}
          type="file"
          accept="image/jpeg,image/png,image/webp"
          aria-label="เลือกรูปเครื่องเขียน"
          disabled={busy || quotaReached}
          onChange={(event) => {
            const file = event.target.files?.[0];
            event.target.value = "";
            if (!file) return;
            if (
              !["image/jpeg", "image/png", "image/webp"].includes(file.type)
            ) {
              setImageError("รองรับเฉพาะรูป JPEG, PNG และ WEBP");
              return;
            }
            if (!file.size || file.size > 5 * 1024 * 1024) {
              setImageError("เลือกรูปที่มีขนาดมากกว่า 0 และไม่เกิน 5 MB");
              return;
            }
            setImageError("");
            setAttachment(draftKey, file);
            ref.current?.focus();
          }}
        />
        {attachment && (
          <div className="attachment-preview">
            <img src={attachment.previewUrl} alt="รูปที่เลือกแนบ" />
            <div>
              <strong>{attachment.file.name}</strong>
              <small>
                {attachment.imageId
                  ? "อัปโหลดแล้ว · ลองส่งใหม่ได้โดยไม่ใช้โควตารูปเพิ่ม"
                  : "แนบ 1 รูป · จะอัปโหลดเมื่อกดส่ง"}
              </small>
            </div>
            <button
              aria-label="นำรูปที่แนบออก"
              disabled={busy}
              onClick={() => setAttachment(draftKey, null)}
            >
              ×
            </button>
          </div>
        )}
        {imageError && (
          <p role="alert" className="error">
            {imageError}
          </p>
        )}
        {attachment && (
          <div className="image-prompts" aria-label="คำถามสำหรับรูปนี้">
            {["มีสินค้านี้ไหม", "ช่วยหาสินค้าที่คล้ายรูปนี้"].map((prompt) => (
              <button
                key={prompt}
                disabled={busy}
                onClick={() =>
                  text && text !== prompt
                    ? setReplacement(prompt)
                    : apply(prompt)
                }
              >
                {prompt}
              </button>
            ))}
          </div>
        )}
        <label htmlFor="draft">ร่างคำถามของคุณ</label>
        <textarea
          ref={ref}
          id="draft"
          placeholder={
            attachment
              ? "ถามเกี่ยวกับรูปนี้ เช่น มีสินค้านี้ไหม"
              : "พิมพ์คำถาม หรือแนบรูปเครื่องเขียนที่อยากหา…"
          }
          value={text}
          disabled={busy}
          maxLength={maxChars}
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
              if (
                !busy &&
                text.length <= maxChars &&
                (text.trim() || attachment) &&
                onSend &&
                (!quotaReached || !attachment || attachment.imageId)
              )
                onSend();
            }
          }}
          aria-describedby="draft-help"
        />
        <div className="flex items-center justify-between gap-3">
          <div className="composer-tools">
            <button
              type="button"
              className="attach-button"
              onClick={() => input.current?.click()}
              disabled={busy || quotaReached}
              aria-label="แนบรูปเครื่องเขียน"
            >
              ＋ รูปภาพ
            </button>
            <button onClick={() => apply("")} disabled={!text || busy}>
              ล้างร่าง
            </button>
          </div>
          <div className="flex items-center gap-3">
            {text.length >= maxChars - 200 && (
              <span aria-live="polite">
                {text.length.toLocaleString()} / {maxChars.toLocaleString()}
              </span>
            )}
            <button
              className="primary"
              disabled={
                busy ||
                text.length > maxChars ||
                (!text.trim() && !attachment) ||
                !onSend ||
                Boolean(quotaReached && attachment && !attachment.imageId)
              }
              onClick={onSend}
            >
              ส่งข้อความ
            </button>
          </div>
        </div>
        <p id="draft-help" className="muted text-sm">
          {remaining !== null ? `รูป Guest เหลือ ${remaining}/3 · ` : ""}JPEG,
          PNG, WEBP ไม่เกิน 5 MB
          <br />
          Enter เพื่อส่ง · Shift+Enter เพื่อขึ้นบรรทัดใหม่
        </p>
        {quotaReached && (
          <p className="muted text-sm">
            ครบโควตารูปแล้ว เข้าสู่ระบบเพื่อแนบรูปต่อได้ การนำรูปออกไม่คืนโควตา
          </p>
        )}
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
