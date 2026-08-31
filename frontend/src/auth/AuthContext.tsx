import { createContext, useContext, useState, type ReactNode } from "react";

// activate {jwt,refresh} 보관 — PR-3. localStorage 백업으로 새로고침 후에도 유지.
// getToken/setToken/clearToken 은 React 트리 밖(api/*.ts)에서도 그대로 쓸 평범한 함수로 둔다.
const STORAGE_KEY_JWT = "moguk_jwt";
const STORAGE_KEY_REFRESH = "moguk_refresh";

export function getToken(): string | null {
  return localStorage.getItem(STORAGE_KEY_JWT);
}

export function getRefreshToken(): string | null {
  return localStorage.getItem(STORAGE_KEY_REFRESH);
}

function persist(jwt: string, refresh: string): void {
  localStorage.setItem(STORAGE_KEY_JWT, jwt);
  localStorage.setItem(STORAGE_KEY_REFRESH, refresh);
}

function wipe(): void {
  localStorage.removeItem(STORAGE_KEY_JWT);
  localStorage.removeItem(STORAGE_KEY_REFRESH);
}

interface AuthContextValue {
  jwt: string | null;
  setToken: (jwt: string, refresh: string) => void;
  clearToken: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [jwt, setJwt] = useState<string | null>(() => getToken());

  function setToken(nextJwt: string, refresh: string) {
    persist(nextJwt, refresh);
    setJwt(nextJwt);
  }

  function clearToken() {
    wipe();
    setJwt(null);
  }

  return (
    <AuthContext.Provider value={{ jwt, setToken, clearToken }}>{children}</AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return ctx;
}
