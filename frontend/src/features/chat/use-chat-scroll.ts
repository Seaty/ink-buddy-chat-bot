"use client";
import { useCallback, useEffect, useRef, useState } from "react";

export function useChatScroll(scope: string, enabled: boolean) {
  const thread = useRef<HTMLDivElement>(null);
  const following = useRef(true);
  const [away, setAway] = useState(false);
  const pause = () => {
    following.current = false;
    setAway(true);
  };
  const latest = useCallback(() => {
    following.current = true;
    setAway(false);
    requestAnimationFrame(() => {
      if (following.current)
        window.scrollTo({
          top: document.documentElement.scrollHeight,
          behavior: "instant",
        });
    });
  }, []);
  useEffect(() => {
    if (!enabled) return;
    following.current = true;
    setAway(false);
    let frame = 0;
    const onScroll = () => {
      const near =
        document.documentElement.scrollHeight -
          window.innerHeight -
          window.scrollY <
        8;
      // Content growth and scroll anchoring also fire scroll events. Only an
      // intentional upward gesture pauses following, not a growing answer.
      if (near) {
        following.current = true;
        setAway(false);
      } else if (!following.current) setAway(true);
    };
    const onWheel = (event: WheelEvent) => {
      if (event.deltaY < 0) {
        following.current = false;
        setAway(true);
      }
    };
    let touchY = 0;
    const onTouchStart = (event: TouchEvent) => {
      touchY = event.touches[0]?.clientY ?? 0;
    };
    const onTouchMove = (event: TouchEvent) => {
      const y = event.touches[0]?.clientY ?? touchY;
      if (y > touchY + 2) {
        following.current = false;
        setAway(true);
      }
      touchY = y;
    };
    const onKey = (event: KeyboardEvent) => {
      if (
        event.target instanceof HTMLElement &&
        event.target.closest("input,textarea,[contenteditable=true]")
      )
        return;
      if (["ArrowUp", "PageUp", "Home"].includes(event.key)) {
        following.current = false;
        setAway(true);
      }
    };
    const onPointer = (event: PointerEvent) => {
      if (
        document.documentElement.clientWidth < window.innerWidth &&
        event.clientX >= document.documentElement.clientWidth
      ) {
        following.current = false;
        setAway(true);
      }
    };
    const observer = new ResizeObserver(() => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        if (following.current) latest();
      });
    });
    if (thread.current) observer.observe(thread.current);
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("wheel", onWheel, { passive: true });
    window.addEventListener("touchstart", onTouchStart, { passive: true });
    window.addEventListener("touchmove", onTouchMove, { passive: true });
    window.addEventListener("keydown", onKey);
    window.addEventListener("pointerdown", onPointer);
    return () => {
      observer.disconnect();
      cancelAnimationFrame(frame);
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("wheel", onWheel);
      window.removeEventListener("touchstart", onTouchStart);
      window.removeEventListener("touchmove", onTouchMove);
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("pointerdown", onPointer);
    };
  }, [scope, latest, enabled]);
  return { thread, away, latest, pause };
}
