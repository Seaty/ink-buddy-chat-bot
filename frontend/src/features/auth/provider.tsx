"use client";
import {
  createContext,
  useContext,
  useEffect,
  useState,
  useRef,
  type ReactNode,
} from "react";
import { uuid7 } from "@/lib/uuid7";
import { api, ApiError, errorText } from "@/lib/api";
import type { Identity, Guest } from "@/lib/types";

export type ImageAttachment = {
  key: string;
  file: File;
  previewUrl: string;
  imageId?: string;
};
type State = {
  identity: Identity | null;
  loading: boolean;
  error: string;
  expired: boolean;
  pendingGuest: Guest | null;
  revision: number;
  messageErrors: Record<string, string>;
  setMessageError: (key: string, value: string) => void;
  drafts: Record<string, string>;
  attachments: Record<string, ImageAttachment>;
  setAttachment: (key: string, file: File | null) => void;
  moveAttachment: (from: string, to: string) => void;
  markImageUploaded: (
    key: string,
    attachmentKey: string,
    imageId: string,
  ) => void;
  refreshGuestQuota: () => Promise<void>;
  attempt: (key: string, content: string) => string;
  clearAttempt: (key: string) => void;
  moveAttempt: (from: string, to: string) => void;
  setDraft: (key: string, value: string) => void;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  claim: () => Promise<void>;
  dismissClaim: () => void;
  recover: () => Promise<void>;
};
const Context = createContext<State | null>(null);
export function AuthProvider({ children }: { children: ReactNode }) {
  const [identity, setIdentity] = useState<Identity | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [expired, setExpired] = useState(false);
  const [pendingGuest, setPendingGuest] = useState<Guest | null>(null);
  const [revision, setRevision] = useState(0);
  const [messageErrors, setMessageErrors] = useState<Record<string, string>>(
    {},
  );
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [attachments, setAttachments] = useState<
    Record<string, ImageAttachment>
  >({});
  const attachmentRef = useRef<Record<string, ImageAttachment>>({});
  function storeAttachments(next: Record<string, ImageAttachment>) {
    attachmentRef.current = next;
    setAttachments(next);
  }
  function clearAttachments() {
    for (const item of Object.values(attachmentRef.current))
      URL.revokeObjectURL(item.previewUrl);
    storeAttachments({});
  }
  function setAttachment(key: string, file: File | null) {
    const next = { ...attachmentRef.current };
    if (next[key]) URL.revokeObjectURL(next[key].previewUrl);
    delete next[key];
    if (file)
      next[key] = { key: uuid7(), file, previewUrl: URL.createObjectURL(file) };
    storeAttachments(next);
  }
  function moveAttachment(from: string, to: string) {
    const item = attachmentRef.current[from];
    if (!item) return;
    const next = { ...attachmentRef.current, [to]: item };
    delete next[from];
    storeAttachments(next);
  }
  function markImageUploaded(
    key: string,
    attachmentKey: string,
    imageId: string,
  ) {
    const item = attachmentRef.current[key];
    if (item?.key === attachmentKey)
      storeAttachments({
        ...attachmentRef.current,
        [key]: { ...item, imageId },
      });
  }
  async function refreshGuestQuota() {
    if (identity?.kind !== "guest") return;
    const guest = await api.currentGuest();
    setIdentity((current) =>
      current?.kind === "guest" && current.guest.id === guest.id
        ? { ...current, guest }
        : current,
    );
  }
  useEffect(
    () => () => {
      for (const item of Object.values(attachmentRef.current))
        URL.revokeObjectURL(item.previewUrl);
    },
    [],
  );
  const attempts = useRef<Record<string, { content: string; id: string }>>({});
  function attempt(key: string, content: string) {
    if (attempts.current[key]?.content !== content)
      attempts.current[key] = { content, id: uuid7() };
    return attempts.current[key].id;
  }
  function clearAttempt(key: string) {
    delete attempts.current[key];
  }
  function moveAttempt(from: string, to: string) {
    if (attempts.current[from]) {
      attempts.current[to] = attempts.current[from];
      delete attempts.current[from];
    }
  }
  function replace(next: Identity | null) {
    clearAttachments();
    setMessageErrors({});
    attempts.current = {};
    setDrafts({});
    setIdentity(next);
    setRevision((v) => v + 1);
  }
  async function recover() {
    setLoading(true);
    setError("");
    try {
      replace(await api.bootstrap());
      setExpired(false);
    } catch (e) {
      setError(errorText(e));
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    let active = true;
    api.onUnauthorized = () => {
      setExpired(true);
      setMessageErrors({});
      attempts.current = {};
      setDrafts({});
      clearAttachments();
      setIdentity(null);
      setRevision((v) => v + 1);
    };
    api
      .bootstrap()
      .then((next) => {
        if (active) replace(next);
      })
      .catch((e) => {
        if (active) setError(errorText(e));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
      api.onUnauthorized = null;
    };
  }, []);
  async function login(email: string, password: string) {
    const guest = identity?.kind === "guest" ? identity.guest : null;
    const profile = await api.login(email, password);
    replace({ kind: "user", profile });
    setExpired(false);
    setPendingGuest(guest);
  }
  async function logout() {
    await api.logout();
    replace(null);
    setPendingGuest(null);
    await recover();
  }
  async function claim() {
    try {
      await api.claim();
      setPendingGuest(null);
      setMessageErrors({});
      attempts.current = {};
      setDrafts({});
      clearAttachments();
      setRevision((v) => v + 1);
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) setPendingGuest(null);
      throw e;
    }
  }
  return (
    <Context.Provider
      value={{
        messageErrors,
        setMessageError: (key, value) =>
          setMessageErrors((e) => ({ ...e, [key]: value })),
        attempt,
        clearAttempt,
        moveAttempt,
        identity,
        loading,
        error,
        expired,
        pendingGuest,
        revision,
        drafts,
        attachments,
        setAttachment,
        moveAttachment,
        markImageUploaded,
        refreshGuestQuota,
        setDraft: (key, value) => setDrafts((d) => ({ ...d, [key]: value })),
        login,
        logout,
        claim,
        dismissClaim: () => setPendingGuest(null),
        recover,
      }}
    >
      {children}
    </Context.Provider>
  );
}
export function useAuth() {
  const value = useContext(Context);
  if (!value) throw new Error("AuthProvider missing");
  return value;
}
