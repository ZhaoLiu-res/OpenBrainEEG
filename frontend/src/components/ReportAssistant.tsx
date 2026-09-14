import { Fragment, useEffect, useRef, useState } from "react";
import { api, json } from "../api";
import "./ReportAssistant.css";

type Message = { role: "user" | "assistant"; content: string; created_at: string; include_summary?: boolean };
type Conversation = { id: string; title: string; job_id: string | null; messages: Message[]; created_at: string; updated_at: string };
type Job = { id: string; filename: string; status: string };
type Connection = { provider: string; model: string };

// React escapes every fragment. Deliberately no HTML or remote image rendering.
function RichText({ text }: { text: string }) {
  const inline = (value: string) => value.split(/(\*\*[^*]+\*\*|`[^`]+`)/g).map((part, i) =>
    part.startsWith("**") && part.endsWith("**") ? <strong key={i}>{part.slice(2, -2)}</strong> :
      part.startsWith("`") && part.endsWith("`") ? <code key={i}>{part.slice(1, -1)}</code> : <Fragment key={i}>{part}</Fragment>);
  return <div className="ra-rich">{text.split(/(```[\s\S]*?```)/g).map((block, i) => block.startsWith("```")
    ? <pre key={i}><code>{block.slice(3, -3).replace(/^[\w+-]*\n/, "")}</code></pre>
    : <div key={i}>{block.split("\n").map((line, j) => /^#{1,6}\s/.test(line)
      ? <h4 key={j}>{inline(line.replace(/^#{1,6}\s+/, ""))}</h4>
      : /^[-*]\s/.test(line) ? <p className="ra-bullet" key={j}>• {inline(line.slice(2))}</p>
        : <p key={j}>{line ? inline(line) : <br />}</p>)}</div>)}</div>;
}

export default function ReportAssistant({ en, initialJobId }: { en: boolean; initialJobId?: string }) {
  const t = (zh: string, english: string) => en ? english : zh;
  const [jobs, setJobs] = useState<Job[]>([]);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [selected, setSelected] = useState("");
  const [draftJob, setDraftJob] = useState("");
  const [question, setQuestion] = useState("");
  const [include, setInclude] = useState(false);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [connection, setConnection] = useState<Connection | null>(null);
  const end = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLTextAreaElement>(null);
  const inFlight = useRef(false);
  const consumedInitialJob = useRef("");
  const active = conversations.find(c => c.id === selected);
  const linkedId = active ? active.job_id || "" : draftJob;
  const linkedJob = jobs.find(j => j.id === linkedId);
  async function refresh() {
    try {
      const [tasks, chats, ai] = await Promise.all([api<Job[]>("/jobs"), api<Conversation[]>("/conversations"), api<Connection>("/ai/settings")]);
      setJobs(tasks.filter(j => j.status === "completed")); setConversations(chats); setConnection(ai); setError("");
    } catch (e) { setError((e as Error).message); } finally { setLoading(false); }
  }
  useEffect(() => { void refresh();
    const reload = () => { if (window.location.hash.startsWith("#/ai")) void refresh(); };
    const settingsChanged = () => { void refresh(); };
    window.addEventListener("hashchange", reload);
    window.addEventListener("brainifly-ai-settings-changed", settingsChanged);
    return () => { window.removeEventListener("hashchange", reload); window.removeEventListener("brainifly-ai-settings-changed", settingsChanged); };
  }, []);
  useEffect(() => {
    if (initialJobId && initialJobId !== consumedInitialJob.current && jobs.some(j => j.id === initialJobId) && !inFlight.current) {
      consumedInitialJob.current = initialJobId;
      setSelected(""); setDraftJob(initialJobId); setInclude(false); setQuestion("");
    }
  }, [initialJobId, jobs.map(j => j.id).join(",")]);
  useEffect(() => { end.current?.scrollIntoView({ block: "nearest" }); }, [selected, active?.messages.length, busy]);
  function newChat() { setSelected(""); setDraftJob(""); setQuestion(""); setInclude(false); setError(""); input.current?.focus(); }
  function openChat(chat: Conversation) { setSelected(chat.id); setQuestion(""); setInclude(false); setError(""); }
  async function send() {
    const text = question.trim();
    if (!text || inFlight.current) return;
    inFlight.current = true; setBusy(true); setError("");
    try {
      let chat = active;
      if (!chat) {
        chat = await api<Conversation>("/conversations", json("POST", { job_id: draftJob || null }));
        setConversations(previous => [chat!, ...previous]); setSelected(chat.id);
      }
      const result = await api<Conversation>(`/conversations/${chat.id}/messages`, json("POST", { question: text, include_summary: !!linkedId && include }));
      setConversations(previous => [result, ...previous.filter(c => c.id !== result.id)]); setQuestion("");
    } catch (e) { setError((e as Error).message); }
    finally { inFlight.current = false; setBusy(false); input.current?.focus(); }
  }
  const prompts = en ? ["Explain the quality metrics and their limits.", "Which cleaning warnings should I investigate first?", "How should I review ASR and ICA results?", "Turn the findings into a practical next-step checklist."]
    : ["解释这份报告的质量指标，以及它们的局限。", "有哪些清洗警告需要优先排查？", "怎样检查 ASR 和 ICA 的处理是否合适？", "把报告结果整理成可执行的下一步清单。"];
  const ready = connection !== null && connection.provider !== "disabled";
  return <section className="report-assistant" aria-label={t("AI 报告助手", "AI report assistant")}>
    <div className="ra-top"><div><h2>{t("报告解释与问答", "Report interpretation & questions")}</h2><p>{t("围绕一份报告持续讨论，也可以直接咨询脑电清洗方法。", "Discuss a report over multiple turns, or ask about EEG cleaning methods.")}</p></div><a className="secondary button" href="#/settings">{t("系统设置 · AI 连接", "System settings · AI connection")}</a></div>
    <div className="ra-workspace">
      <div className="ra-history"><button disabled={busy || loading} onClick={newChat}>＋ {t("新建对话", "New conversation")}</button><h3>{t("本机对话记录", "Conversations on this device")}</h3>
        {loading ? <p role="status">{t("正在读取…", "Loading…")}</p> : conversations.length === 0 ? <p className="muted">{t("首次发送后，对话会保存在本机。", "Your first conversation will be saved here after sending.")}</p> : conversations.map(chat => <button className={`ra-chat-link ${selected === chat.id ? "selected" : ""}`} key={chat.id} disabled={busy} onClick={() => openChat(chat)}><strong>{chat.title || t("新对话", "New conversation")}</strong><span>{chat.job_id ? t("报告问答", "Report discussion") : t("方法咨询", "Methods discussion")} · {new Date(chat.updated_at).toLocaleDateString(en ? "en-US" : "zh-CN")}</span></button>)}
      </div>
      <div className="ra-discussion" aria-busy={busy}>
        <div className="ra-context"><label htmlFor="ra-job">{t("关联报告", "Linked report")}</label><select id="ra-job" value={linkedId} disabled={busy || !!active} onChange={e => { setDraftJob(e.target.value); setInclude(false); }}><option value="">{t("不关联 · 通用脑电问题", "No report · General EEG questions")}</option>{jobs.map(job => <option key={job.id} value={job.id}>{job.filename}</option>)}</select>{linkedId && <a href={`#/reports/${linkedId}`}>{t("查看报告", "View report")}</a>}<span className="ra-model">{ready ? connection.model : t("AI 尚未启用", "AI is not enabled")}</span></div>
        {active && <p className="ra-context-note">{t("当前对话固定关联报告；讨论另一份报告请新建对话。", "A conversation keeps its linked report. Start a new one to discuss a different report.")}</p>}
        <div className="ra-messages" role="log" aria-label={t("对话消息", "Conversation messages")} aria-live="polite">
          {!active?.messages.length && <div className="ra-empty"><h3>{linkedJob ? t("从这份报告开始", "Start with this report") : t("把结果变成下一步行动", "Find your next step")}</h3><p>{linkedJob?.filename || t("选择报告后，可以分享质量指标、处理参数和警告；也可以不关联报告直接提问。", "Choose a report to share quality metrics, processing parameters and warnings, or ask without a report.")}</p><div className="ra-prompts">{prompts.map(prompt => <button className="secondary" key={prompt} disabled={busy} onClick={() => { setQuestion(prompt); input.current?.focus(); }}>{prompt}</button>)}</div></div>}
          {active?.messages.map((message, i) => <article className={`ra-message ${message.role}`} key={`${active.id}-${i}`}><div className="ra-message-heading"><strong>{message.role === "user" ? t("你", "You") : t("报告助手", "Report assistant")}</strong>{message.include_summary && <span>{t("已附报告摘要", "Report summary included")}</span>}</div><RichText text={message.content} /></article>)}
          {busy && <div className="ra-pending" role="status">{t("模型正在回答，请稍候…", "The model is responding. Please wait…")}</div>}<div ref={end} />
        </div>
        <form className="ra-composer" onSubmit={e => { e.preventDefault(); void send(); }}>
          {!ready && !loading && <p className="ra-notice">{t("先到系统设置启用本地模型或 API 服务，再开始提问。", "Enable a local model or API provider in system settings before asking.")} <a href="#/settings">{t("配置 AI", "Configure AI")}</a></p>}
          {error && <div className="error" role="alert">{error}<p>{t("问题已保留，检查系统设置后可再次发送。", "Your question is preserved. Check system settings, then send again.")} <button type="button" className="secondary" disabled={busy} onClick={() => void refresh()}>{t("刷新连接状态", "Refresh connection status")}</button></p></div>}
          <label className="ra-share"><input type="checkbox" checked={include} disabled={!linkedId || busy} onChange={e => setInclude(e.target.checked)} />{t("本次附带关联报告的指标、参数和警告摘要", "Include this report's metrics, parameters and warnings in this request")}</label>
          <p className="ra-privacy">{t("问题和当前对话历史会发送给系统设置中选定的 AI 服务（更换服务后也如此）。不发送原始脑电文件。历史回答可能包含之前分享过的报告信息。", "Your question and this conversation's history are sent to the AI service selected in system settings, including after switching providers. Raw EEG files are not sent. Earlier answers may contain previously shared report information.")}</p>
          <label className="sr-only" htmlFor="ra-question">{t("输入问题", "Your question")}</label><textarea id="ra-question" ref={input} value={question} maxLength={12000} disabled={busy} rows={3} placeholder={t("输入问题，例如：坏导比例偏高，应如何检查？", "Ask a question, e.g. how should I investigate a high bad-channel ratio?")} onChange={e => setQuestion(e.target.value)} onKeyDown={e => { if ((e.ctrlKey || e.metaKey) && e.key === "Enter" && !e.nativeEvent.isComposing) { e.preventDefault(); if (ready) void send(); } }} />
          <div className="ra-send-row"><small>{t("Ctrl / ⌘ + Enter 发送 · 回答仅用于科研辅助", "Ctrl / ⌘ + Enter to send · Research assistance only")}</small><button type="submit" disabled={busy || loading || !ready || !question.trim()}>{busy ? t("正在回答…", "Responding…") : t("发送问题", "Send question")}</button></div>
        </form>
      </div>
    </div>
  </section>;
}
