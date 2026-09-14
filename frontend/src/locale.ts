import { useEffect, useState } from "react";
import { api } from "./api";
type Language = "zh" | "en";
type Mode = Language | "auto";
export function browserLanguage(languages: readonly string[]): Language {
  for (const language of languages) {
    if (/^zh(?:-|$)/i.test(language)) return "zh";
    if (/^en(?:-|$)/i.test(language)) return "en";
  }
  return "en";
}
export function useLanguage() {
  const [mode, setMode] = useState<Mode>(() => {
    const value = localStorage.getItem("brainifly-language-mode");
    return value === "zh" || value === "en" ? value : "auto";
  });
  const [detected, setDetected] = useState<Language>(() => browserLanguage(navigator.languages));
  const [source, setSource] = useState("browser");
  const lang = mode === "auto" ? detected : mode;
  useEffect(() => {
    if (mode !== "auto") return;
    let active = true;
    api<{ language: Language | null; source: string }>("/locale").then(data => {
      if (active) { setDetected(data.language || browserLanguage(navigator.languages)); setSource(data.source); }
    }).catch(() => { if (active) { setDetected(browserLanguage(navigator.languages)); setSource("browser"); } });
    return () => { active = false; };
  }, [mode]);
  useEffect(() => { document.documentElement.lang = lang === "zh" ? "zh-CN" : "en"; }, [lang]);
  const changeMode = (value: Mode) => { localStorage.setItem("brainifly-language-mode", value); setMode(value); };
  return { lang, mode, changeMode, source };
}
