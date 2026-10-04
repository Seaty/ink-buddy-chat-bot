"use client";
import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { api, ApiError, errorText } from "@/lib/api";
import type { Identity, Guest } from "@/lib/types";

type State = {
  identity: Identity | null;
  loading: boolean;
  error: string;
  expired: boolean;
  pendingGuest: Guest | null;
  revision: number;
  drafts: Record<string, string>;
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
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  function replace(next: Identity | null) {
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
      setDrafts({});
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
      setDrafts({});
      setRevision((v) => v + 1);
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) setPendingGuest(null);
      throw e;
    }
  }
  return (
    <Context.Provider
      value={{
        identity,
        loading,
        error,
        expired,
        pendingGuest,
        revision,
        drafts,
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
