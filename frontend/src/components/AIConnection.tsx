import { useEffect, useState } from "react";
import { api, json } from "../api";

type Settings = { provider: "disabled" | "ollama" | "openai_compatible" | "anthropic"; base_url: string; model: string; timeout_seconds: number; has_api_key: boolean; history_turns: number; max_output_tokens: number };
type Mode = "local" | "api";
type PresetConfig = {id:string;name:string;base_url:string;model:string;mode:Mode;provider:Settings["provider"];documentation:string};
function localURL(value: string) { try { return ["localhost", "127.0.0.1", "[::1]"].includes(new URL(value).hostname); } catch { return false; } }

export default function AIConnection({ en, onReadyChange }: { en: boolean; onReadyChange?: (ready: boolean) => void }) {
  const t = (zh: string, english: string) => en ? english : zh;
  const [settings, setSettings] = useState<Settings>({ provider: "disabled", base_url: "http://localhost:11434", model: "", timeout_seconds: 120, has_api_key: false, history_turns:10, max_output_tokens:2048 });
  const [enabled, setEnabled] = useState(false);
  const [mode, setMode] = useState<Mode>("local");
  const [preset, setPreset] = useState("ollama");
  const [catalog, setCatalog] = useState<PresetConfig[]>([]);
  const [models, setModels] = useState<string[]>([]);
  const presets: Record<string,PresetConfig> = Object.fromEntries(catalog.map(p=>[p.id,p]));
  presets.custom = {id:"custom",name:t("自定义服务","Custom service"),provider:"openai_compatible",base_url:mode==="local"?"http://localhost:1234/v1":"https://",model:"",mode,documentation:""};
  const [key, setKey] = useState("");
  const [clearKey, setClearKey] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  useEffect(() => { onReadyChange?.(loaded && enabled && !dirty && !busy); }, [loaded, enabled, dirty, busy, onReadyChange]);
  useEffect(() => {
    let active = true;
    Promise.all([api<Settings>("/ai/settings"),api<PresetConfig[]>("/ai/providers")]).then(([data,providers]) => {
      if (!active) return;
      setCatalog(providers); setSettings(data); setEnabled(data.provider !== "disabled"); setMode(localURL(data.base_url) ? "local" : "api");
      setPreset(providers.find(p=>p.base_url === data.base_url)?.id || "custom"); setLoaded(true);
    }).catch(e => { if (active) setError(e.message); });
    return () => { active = false; };
  }, []);
  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ""; };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);
  function choose(value: string) {
    const next = presets[value]; if(!next)return; setEnabled(true); setDirty(true); if(value === preset && settings.base_url === next.base_url)return; setModels([]); setPreset(value); setKey(""); setClearKey(true); setDirty(true); setMessage("");
    setSettings(s => ({ ...s, provider: next.provider, base_url: value === "custom" && mode === "local" ? "http://localhost:1234/v1" : next.base_url, model: next.model, has_api_key: false }));
  }
  function changeMode(value: Mode) { setMode(value); choose(value === "local" ? "ollama" : "deepseek"); }
  function update(values: Partial<Settings>) { setSettings(s => ({ ...s, ...values })); setDirty(true); setMessage(""); }
  function draft(activate = enabled): Settings & {api_key:string|null} {
    return {...settings, model:settings.model.trim(), provider:activate ? (settings.provider === "disabled" ? presets[preset]?.provider || "openai_compatible" : settings.provider) : "disabled", api_key:key.trim() || (clearKey ? "" : null)};
  }
  async function loadModels() {
    setBusy(true);setError("");setMessage(t("正在读取模型…","Loading models…"));
    try { const result=await api<{models:string[]}>("/ai/models",json("POST",draft(true)));setModels(result.models);setMessage(result.models.length?t("模型列表已更新，请选择对话模型。","Model list updated. Select a chat model."):t("服务没有返回模型，请手动填写。","No models returned; enter a model manually.")); }
    catch(e){setMessage("");setError((e as Error).message);}finally{setBusy(false);}
  }
  async function save(testAfter = false) {
    const activate = enabled || testAfter;
    setError(""); setMessage("");
    if (activate && !settings.model.trim()) { setError(t("请填写已安装或服务支持的模型名称。", "Enter an installed or supported model name.")); return; }
    if (activate && mode === "api" && !key.trim() && (!settings.has_api_key || clearKey)) { setError(t("请填写服务商提供的 API Key。", "Enter your provider's API key.")); return; }
    if (activate && mode === "local" && !localURL(settings.base_url)) { setError(t("本地接入请使用 localhost 或 127.0.0.1 地址。", "Local connections must use localhost or 127.0.0.1.")); return; }
    if (activate && mode === "api" && !settings.base_url.trim().startsWith("https://")) { setError(t("API 服务地址必须使用 HTTPS。", "API providers require an HTTPS URL.")); return; }
    setBusy(true);
    try {
      const data = await api<Settings>("/ai/settings", json("PUT", draft(activate)));
      window.dispatchEvent(new Event("brainifly-ai-settings-changed"));
      setEnabled(activate);
      setSettings(data); setKey(""); setClearKey(false); setDirty(false); setMessage(t("设置已保存。", "Settings saved."));
      if(testAfter){const result=await api<{model:string}>("/ai/test", {method:"POST"});setMessage(t("连接成功，模型：","Connected. Model: ")+result.model);}
    } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }
  return <div className="card ai-connection"><h2>{t("AI 服务配置", "AI service configuration")}</h2><p className="muted">{t("选择本机模型或 API 服务。数据清洗不依赖 AI。", "Choose a local model or an API provider. EEG cleaning works independently.")}</p>
    <fieldset disabled={!loaded || busy}><legend className="sr-only">{t("AI 连接设置", "AI connection settings")}</legend>
      <div className="ai-mode-grid" role="group" aria-label={t("接入方式", "Connection method")}>
        <button type="button" aria-pressed={mode === "local"} className={`mode-card ${mode === "local" ? "active" : ""}`} onClick={() => changeMode("local")}><strong>{t("本地模型", "Local model")}</strong><span>Ollama / LM Studio</span></button>
        <button type="button" aria-pressed={mode === "api"} className={`mode-card ${mode === "api" ? "active" : ""}`} onClick={() => changeMode("api")}><strong>{t("API Key 接入", "API key")}</strong><span>DeepSeek / Kimi</span></button>
      </div>
      <label className="check"><input type="checkbox" checked={enabled} onChange={e => { setEnabled(e.target.checked); setDirty(true); }}/>{t("启用 AI 助手", "Enable AI assistant")}</label>
      <label className="provider-picker">{t("服务", "Service")}<select name="ai-service" value={preset} onChange={e => choose(e.target.value)}>{[...catalog.filter(p=>p.mode===mode),presets.custom].map(p=><option value={p.id} key={p.id}>{p.name}</option>)}</select></label>
      <label>{t("接口协议", "API protocol")}<select value={settings.provider === "disabled" ? presets[preset]?.provider || "openai_compatible" : settings.provider} onChange={e=>update({provider:e.target.value as Settings["provider"]})}><option value="openai_compatible">Chat Completions</option><option value="ollama">Ollama</option><option value="anthropic">Anthropic Messages</option></select></label>
      <label>{t("服务地址", "Service URL")}<input name="ai-base-url" type="url" autoComplete="off" spellCheck={false} value={settings.base_url} onChange={e => { update({ base_url: e.target.value, has_api_key: false }); setKey(""); setClearKey(true); }}/></label>
      <label>API Key {mode === "local" && t("（可选）", "(optional)")}<input name="ai-api-key" type="password" autoComplete="off" spellCheck={false} value={key} onChange={e => { setKey(e.target.value); setClearKey(!e.target.value && clearKey); setDirty(true); }} placeholder={settings.has_api_key ? t("已保存，留空保留…", "Saved; leave blank to preserve…") : t("粘贴 API Key…", "Paste API key…")}/></label>
      {settings.has_api_key && <label className="check"><input type="checkbox" checked={clearKey} onChange={e => { setClearKey(e.target.checked); setDirty(true); }}/>{t("清除已保存的密钥", "Clear saved key")}</label>}
      <button type="button" className="secondary" onClick={loadModels}>{t("读取可用模型", "Load available models")}</button>
      {models.length > 0 && <label>{t("可用模型（选择文本对话模型）", "Available models (choose a text chat model)")}<select value="" onChange={e=>update({model:e.target.value})}><option value="" disabled>{t("选择模型…", "Select a model…")}</option>{models.map(m=><option key={m}>{m}</option>)}</select></label>}
      <label>{t("模型名称", "Model name")}<input name="ai-model" autoComplete="off" spellCheck={false} value={settings.model} onChange={e => update({ model: e.target.value })} placeholder={t("填写模型名称…", "Enter a model name…")}/></label>
      <p className="muted">{mode === "local" ? t("先启动 Ollama 或 LM Studio 的服务，再填写其中已安装的模型名称。", "Start Ollama or the LM Studio server and enter an installed model name.") : t("已填入服务商预设；模型名可按你的账户权限修改。", "Provider defaults are filled in; change the model to one available to your account.")}</p>
      <label>{t("响应超时（秒）", "Response timeout (seconds)")}<input name="ai-timeout" type="number" min={5} max={600} value={settings.timeout_seconds} onChange={e => update({ timeout_seconds: Number(e.target.value) })}/></label>
      <div className="fields"><label>{t("历史对话轮数", "History turns")}<input type="number" min={0} max={40} value={settings.history_turns} onChange={e=>update({history_turns:Number(e.target.value)})}/></label><label>{t("最大输出 tokens", "Output token limit")}<input type="number" min={128} max={16384} value={settings.max_output_tokens} onChange={e=>update({max_output_tokens:Number(e.target.value)})}/></label></div>
      <div className="actions"><button type="button" className="primary" onClick={()=>save()}>{busy ? t("处理中…", "Working…") : t("保存设置", "Save settings")}</button><button type="button" className="secondary" onClick={()=>save(true)}>{t("保存并测试连接", "Save & test connection")}</button></div>
    </fieldset>
    {presets[preset]?.documentation && <p><a href={presets[preset].documentation} target="_blank" rel="noreferrer">{t("服务商配置文档", "Provider documentation")}</a></p>}
    <p className="muted">{dirty ? t("有未保存的设置，请先保存再提问。", "Unsaved settings. Save before asking.") : t("测试连接会发送一条短请求，API 服务可能计费。不会发送脑电数据。", "Testing sends a short request; API providers may charge for it. No EEG data is sent.")}</p>
    <p className="muted">{t("密钥仅保存在本机配置文件，不写入浏览器存储。", "Keys are saved in a local configuration file, never in browser storage.")}</p>
    {message && <div className="connection-status" role="status">{message}</div>}{error && <div className="alert error" role="alert">{error}</div>}
  </div>;
}
