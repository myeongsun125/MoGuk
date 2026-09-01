import { createContext, useContext, useState, type ReactNode } from "react";

// activate {jwt,refresh} 보관 — PR-3. localStorage 백업으로 새로고침 후에도 유지.
// getToken/setToken/clearToken 은 React 트리 밖(api/*.ts)에서도 그대로 쓸 평범한 함수로 둔다.
//
// D-4 ② 삼성인터넷 대응: 일부 브라우저(삼성인터넷 포함)는 설정에 따라 localStorage
// 읽기/쓰기를 막거나 조용히 비운다 — 그 상태에서 confirm 등 인증 API를 부르면 토큰이
// null 로 읽혀 401 로 이어진다. 그래서 인메모리 캐시(memJwt/memRefresh)를 진실원본
// 우선순위 1번으로 두고, localStorage는 "가능하면 유지되는" 새로고침 대비 백업으로
// 격하한다 — 접근 자체가 막힌 브라우저에서도 세션 내(새로고침 전까지)는 토큰이
// 살아있어 confirm 200 이 나온다. 새로고침하면 메모리는 당연히 소멸하고 localStorage
// 폴백으로 넘어가며, 그마저 막힌 브라우저에서는 재활성화가 필요해진다(이 PR 스코프 밖).
const STORAGE_KEY_JWT = "moguk_jwt";
const STORAGE_KEY_REFRESH = "moguk_refresh";

let memJwt: string | null = null;
let memRefresh: string | null = null;

export function getToken(): string | null {
  if (memJwt !== null) return memJwt;
  try {
    return localStorage.getItem(STORAGE_KEY_JWT);
  } catch {
    return null;
  }
}

export function getRefreshToken(): string | null {
  if (memRefresh !== null) return memRefresh;
  try {
    return localStorage.getItem(STORAGE_KEY_REFRESH);
  } catch {
    return null;
  }
}

function persist(jwt: string, refresh: string): void {
  memJwt = jwt;
  memRefresh = refresh;
  try {
    localStorage.setItem(STORAGE_KEY_JWT, jwt);
    localStorage.setItem(STORAGE_KEY_REFRESH, refresh);
  } catch {
    // 저장 차단 브라우저 — 인메모리만으로 세션 내 유지, 새로고침 시엔 재활성화 필요.
  }
}

function wipe(): void {
  memJwt = null;
  memRefresh = null;
  try {
    localStorage.removeItem(STORAGE_KEY_JWT);
    localStorage.removeItem(STORAGE_KEY_REFRESH);
  } catch {
    // 접근 차단 브라우저 — 이미 메모리는 비웠으니 무시.
  }
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
