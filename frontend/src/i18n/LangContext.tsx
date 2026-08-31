import { createContext, useContext, useMemo, useState, type ReactNode } from "react";
import { MESSAGES } from "./messages";
import type { Lang } from "../api/types";

// AuthContext(auth/AuthContext.tsx)와 동형 — localStorage 백업으로 새로고침 후에도 유지(#61 판정A).
const STORAGE_KEY = "moguk_lang";
const VALID_LANGS: Lang[] = ["vi", "ko", "in"];

function getStoredLang(): Lang | null {
  const raw = localStorage.getItem(STORAGE_KEY);
  return raw !== null && (VALID_LANGS as string[]).includes(raw) ? (raw as Lang) : null;
}

interface LangContextValue {
  lang: Lang;
  setLang: (lang: Lang) => void;
  t: (key: string) => string;
}

const LangContext = createContext<LangContextValue | null>(null);

// 기본 vi — 근로자 대상 언어 (skeleton §0-3 참고, workers.lang CHECK IN ('vi','in')).
// 초기값 우선순위: 저장값 > vi. 활성화 성공 시 응답 lang이 저장값을 덮는다(Invite/index.tsx).
export function LangProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(() => getStoredLang() ?? "vi");

  function setLang(next: Lang) {
    localStorage.setItem(STORAGE_KEY, next);
    setLangState(next);
  }

  const value = useMemo<LangContextValue>(
    () => ({
      lang,
      setLang,
      t: (key: string) => MESSAGES[lang][key] ?? key,
    }),
    [lang],
  );

  return <LangContext.Provider value={value}>{children}</LangContext.Provider>;
}

export function useLang(): LangContextValue {
  const ctx = useContext(LangContext);
  if (!ctx) {
    throw new Error("useLang must be used within LangProvider");
  }
  return ctx;
}
