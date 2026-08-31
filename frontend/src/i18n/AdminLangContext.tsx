import { createContext, useContext, useMemo, useState, type ReactNode } from "react";
import { MESSAGES } from "./messages";
import type { Lang } from "../api/types";

// LangContext(워커, moguk_lang)와 동형이지만 완전히 별개 컨텍스트/저장키(#63) — 관리자
// 화면 언어가 워커 화면 언어에 영향을 주거나 받지 않는다.
const STORAGE_KEY = "moguk_admin_lang";
const VALID_LANGS: Lang[] = ["vi", "ko", "in"];

function getStoredAdminLang(): Lang | null {
  const raw = localStorage.getItem(STORAGE_KEY);
  return raw !== null && (VALID_LANGS as string[]).includes(raw) ? (raw as Lang) : null;
}

interface AdminLangContextValue {
  lang: Lang;
  setLang: (lang: Lang) => void;
  t: (key: string) => string;
}

const AdminLangContext = createContext<AdminLangContextValue | null>(null);

// 기본 ko — 관리자는 한국어 스태프 가정(워커 기본 vi와 다름). 초기값 우선순위: 저장값 > ko.
export function AdminLangProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(() => getStoredAdminLang() ?? "ko");

  function setLang(next: Lang) {
    localStorage.setItem(STORAGE_KEY, next);
    setLangState(next);
  }

  const value = useMemo<AdminLangContextValue>(
    () => ({
      lang,
      setLang,
      t: (key: string) => MESSAGES[lang][key] ?? key,
    }),
    [lang],
  );

  return <AdminLangContext.Provider value={value}>{children}</AdminLangContext.Provider>;
}

export function useAdminLang(): AdminLangContextValue {
  const ctx = useContext(AdminLangContext);
  if (!ctx) {
    throw new Error("useAdminLang must be used within AdminLangProvider");
  }
  return ctx;
}
