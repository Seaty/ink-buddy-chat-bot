"use client";
import { useEffect, useRef, type ReactNode } from "react";
export function Dialog({
  title,
  children,
  onClose,
}: {
  title: string;
  children: ReactNode;
  onClose: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const close = useRef(onClose);
  close.current = onClose;
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    ref.current?.showModal();
    return () => {
      ref.current?.close();
      previous?.focus();
    };
  }, []);
  return (
    <dialog
      ref={ref}
      aria-label={title}
      onCancel={(e) => {
        e.preventDefault();
        close.current();
      }}
      className="modal"
    >
      <div className="flex items-center justify-between gap-4">
        <h2>{title}</h2>
        <button aria-label="ปิด" onClick={onClose}>
          ✕
        </button>
      </div>
      {children}
    </dialog>
  );
}
