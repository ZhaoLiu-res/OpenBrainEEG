import React, { useEffect, useState } from "react";
import ReactDOM from "react-dom/client";
import "./style.css";
import { api, json } from "./api";
import { useLanguage } from "./locale";
import SystemSettings, { defaultPreferences, type Preferences } from "./components/SystemSettings";
import ReportExports, { type ExportState } from "./components/ReportExports";
import ReportAssistant from "./components/ReportAssistant";
import HelpCenter from "./components/HelpCenter";
import SignalIllustration from "./components/SignalIllustration";

type Job = { exports?:Record<string,ExportState>; id: string; created_at?: string; config?: unknown; steps?: unknown; filename: string; status: string; progress: number; step: string; warnings: string[]; error: string | null; outputs: Record<string,string>; metrics?: Record<string,unknown>; dataset: { n_channels: number; duration: number; sfreq: number } };
type Demo = { id: string; filename: string; name: string; name_en: string; available: boolean };
function App() {
  const { lang, mode: languageMode, changeMode: changeLanguageMode, source: languageSource } = useLanguage();
  const en = lang === "en";
  const t = (zh: string, english: string) => en ? english : zh;
  const [route, setRoute] = useState(location.hash.slice(2) || "home");
  const tab = route.split("/")[0];
  const setTab = (page: string) => { location.hash = "/" + page; };
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("all");
  const [loaded, setLoaded] = useState(false);
  useEffect(() => { const update = () => setRoute(location.hash.slice(2) || "home"); window.addEventListener("hashchange", update); return () => window.removeEventListener("hashchange", update); }, []);
  const [demos, setDemos] = useState<Demo[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [selected, setSelected] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [asr, setAsr] = useState(true);
  const [ica, setIca] = useState(true);
  const [pdf, setPdf] = useState(false);
  const [low, setLow] = useState(0.5);
  const [high, setHigh] = useState(40);
  const [notch, setNotch] = useState(50);
  const [preferences, setPreferences] = useState<Preferences>(defaultPreferences);
  const [preferencesLoaded, setPreferencesLoaded] = useState(false);
  useEffect(()=>{api<Preferences>("/settings").then(value=>{setPreferences(value);setPdf(value.default_pdf);setPreferencesLoaded(true);}).catch(e=>setError(e.message));},[]);
  useEffect(() => {
    api<Demo[]>("/demos").then(setDemos).catch(e => setError(e.message));
    let active = true;
    const refresh = () => api<Job[]>("/jobs").then(data => { if (active) { setJobs(data); setLoaded(true); } }).catch(e => { if (active) setError(e.message); });
    refresh(); const timer = setInterval(refresh, 2000);
    return () => { active = false; clearInterval(timer); };
  }, []);
  const config = () => ({ filter: { l_freq: low, h_freq: high, notch_freq: notch }, asr: { enabled: asr }, ica: { enabled: ica }, report_language: preferences.report_language === "auto" ? lang : preferences.report_language, report_formats: pdf ? ["html", "pdf"] : ["html"] });
  async function submit(demo?: string) {
    setBusy(true); setError(""); setNotice("");
    try {
      let item: Job;
      if (demo) item = await api<Job>(`/demos/${demo}`, json("POST", config()));
      else { if (!file) throw new Error(t("请先选择文件", "Choose a recording first")); if(file.size > preferences.max_upload_mb*1024*1024) throw new Error(t("文件超过系统设置的大小限制", "File exceeds the limit in System settings")); const form = new FormData(); form.append("file", file); form.append("config_json", JSON.stringify(config())); item = await api<Job>("/jobs", { method: "POST", body: form }); }
      setJobs(items => [item, ...items.filter(j => j.id !== item.id)]); setSelected(item.id); setTab(`jobs/${item.id}`);
    } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }
  const status = (j: Job) => ({queued:t("等待中","Queued"),running:t("处理中","Running"),completed:t("已完成","Completed"),failed:t("失败","Failed")}[j.status] || j.status);
  const current = jobs.find(j => j.id === route.split("/")[1]);
  useEffect(() => {
    if (preferences.auto_open_report && tab === "jobs" && current?.status === "completed") location.replace(`#/reports/${current.id}`);
  }, [tab, current?.id, current?.status, preferences.auto_open_report]);
  const names: Record<string,string> = {help:t("使用文档","User guide"),copyright:t("版权信息","Copyright"),settings:t("系统设置","System settings"),home:t("首页","Home"),samples:t("样例运行","Samples"),clean:t("数据清洗","EEG cleaning"),history:t("历史任务与报告","History & reports"),ai:t("AI 报告助手","AI assistant"),jobs:t("任务进度","Job progress"),reports:t("报告查看","Report viewer")};
  const date = (j: Job) => j.created_at ? new Date(j.created_at).toLocaleString(en ? "en-US" : "zh-CN") : "—";
  const openJob = (j: Job) => setTab(`${j.status === "completed" ? "reports" : "jobs"}/${j.id}`);
  const downloads = (j: Job) => <div className="downloads">{Object.keys(j.outputs).filter(kind=>!["pdf","research_figures"].includes(kind)).map(kind => <a key={kind} href={`/api/jobs/${j.id}/files/${kind}`}>{kind === "html" ? t("下载 HTML 报告","Download HTML report") : kind === "parameters" ? t("处理参数 JSON","Parameters JSON") : kind.toUpperCase()} ↓</a>)}</div>;
  const history = (items: Job[]) => !items.length ? <div className="empty">{t("暂无匹配任务。可以先运行样例或导入数据。","No matching jobs. Run a sample or import a recording.")} <button className="secondary" onClick={()=>setTab("samples")}>{names.samples} →</button></div> : <div className="table-scroll"><table><thead><tr>{[t("文件 / 任务","Recording / job"),t("创建时间","Created"),t("状态","Status"),t("质量评分","Quality score"),t("操作","Actions")].map(h=><th key={h}>{h}</th>)}</tr></thead><tbody>{items.map(j=><tr key={j.id}><td><strong>{j.filename}</strong><small>{j.dataset.n_channels} {t("通道","channels")} · {j.dataset.sfreq} Hz · {j.dataset.duration.toFixed(1)} s</small></td><td>{date(j)}</td><td><span className={`badge ${j.status}`}>{status(j)}{["queued","running"].includes(j.status) && ` · ${j.progress}%`}</span>{j.warnings.length > 0 && <small>{j.warnings.length} {t("条警告","warnings")}</small>}</td><td>{String(j.metrics?.quality_score ?? "—")}</td><td><button className="secondary" onClick={()=>openJob(j)}>{j.status === "completed" ? t("查看报告","View report") : t("查看任务","View job")} →</button></td></tr>)}</tbody></table></div>;
  return <div className="shell">
    <a className="skip-link" href="#main-content" onClick={e=>{e.preventDefault();document.getElementById("main-content")?.focus();}}>{t("跳转到主要内容", "Skip to main content")}</a>
    <aside><a className="brand" href="#/home"><img src="/brainifly-icon-wave.svg" alt="" width="36" height="36"/><span>Brainifly<small>{t("脑电研究工作台", "EEG research workspace")}</small></span></a>
      <nav aria-label={t("主导航","Main navigation")}>{["home","samples","clean","history","ai","settings","help","copyright"].map(page=><a key={page} href={`#/${page}`} aria-current={tab===page ? "page" : undefined} className={tab===page || (page==="history" && ["jobs","reports"].includes(tab)) ? "active" : ""}>{names[page]}</a>)}</nav>
      <div className="side-note"><span className="dot"/>{t("本地运行 · 无需登录","Local · No login")}<p>{t("任务与结果持续保存在本机，重启后可从历史记录继续查看。","Jobs and results persist on this computer and remain available after restart.")}</p></div>
    </aside>
    <main id="main-content" tabIndex={-1}><header><span className="eyebrow">{names[tab] || "Brainifly"}</span><label className="language-picker"><span>{t("语言", "Language")}</span><select aria-label={t("界面语言", "Interface language")} value={languageMode} onChange={e=>changeLanguageMode(e.target.value as "auto"|"zh"|"en")}><option value="auto">{t("自动 / IP", "Auto / IP")}</option><option value="zh">中文</option><option value="en">English</option></select></label></header>
      {error && <div className="alert error" role="alert">{error}<button aria-label={t("关闭提示", "Dismiss message")} onClick={()=>setError("")}>×</button></div>}{notice && <div className="alert" role="status">{notice}</div>}
      {tab !== "home" && <div className="page-heading"><h1>{names[tab] || t("页面不存在","Page not found")}</h1><p className="subtitle">{tab === "help" ? t("按步骤开始，遇到问题随时查阅。", "Follow the steps and find answers when needed.") : tab === "copyright" ? t("个人使用权限、商用授权和分析结果的使用边界。", "Personal permissions, commercial authorization and limits of analysis.") : t("从样例到自己的数据，从处理进度到完整报告。","From samples to your recordings, from processing to full reports.")}</p></div>}
      {tab === "home" && <>
        <section className="hero"><div><h1>{t("从脑电信号，\n到可检查的研究结果。","From EEG signals\nto reviewable results.")}</h1><p>{t("Brainifly 将脑电清洗、质量评估和可视化报告连接在一个本地工作台中。无需登录，导入数据即可开始；每一次处理都有记录可查。","Brainifly connects EEG cleaning, quality assessment and visual reports in one local workspace. No login required. Import a recording and keep every result accessible.")}</p><div className="actions"><button className="primary" onClick={()=>setTab("clean")}>{t("导入数据并清洗","Import & clean")} →</button><button className="secondary" onClick={()=>setTab("samples")}>{t("先运行一个样例","Try a sample")}</button></div></div><SignalIllustration en={en}/></section>
        <section className="feature-grid">{[[t("完整的处理流程","Processing pipeline"),t("滤波、坏导处理、重参考、ASR 与 ICA/ICLabel，沿用原版科学计算核心。","Filtering, bad-channel handling, rereferencing, ASR and ICA/ICLabel, using the original scientific core.")],[t("报告就在工作台里","Reports in your workspace"),t("处理完成自动进入报告页，检查图表、质量指标和警告，也可下载离线 HTML。","Open reports automatically after processing. Review charts, metrics and warnings, or download offline HTML.")],[t("可选的 AI 解读","Optional AI assistance"),t("连接本地模型或兼容 API，按需发送问题和报告摘要。不开启 AI 也能完成清洗。","Connect a local model or compatible API and send questions and summaries when needed. Cleaning works without AI.")]].map(([title,desc])=><article className="card" key={title}><h2>{title}</h2><p>{desc}</p></article>)}</section>
        <section className="card"><div className="section-title"><h2>{t("最近任务","Recent jobs")}</h2><button className="secondary" onClick={()=>setTab("history")}>{t("查看全部","View all")} →</button></div>{history(jobs.slice(0,5))}</section>
      </>}
      {tab === "clean" && <>        <section className="grid"><div className="card"><div className="section-title"><span className="number">01</span><h2>{t("导入记录", "Import recording")}</h2></div>
          <label className="drop"><span className="upload-icon">↥</span><strong>{file?.name || t("选择一个脑电文件", "Choose an EEG recording")}</strong><span>EDF · BDF · GDF · FIF · OpenBCI TXT · BrainFlow CSV</span><input aria-label={t("脑电文件", "EEG recording")} type="file" accept=".edf,.bdf,.gdf,.fif,.txt,.csv" onChange={e => setFile(e.target.files?.[0] || null)}/></label>
          <p className="muted">{t(`单文件最大 ${preferences.max_upload_mb} MB，可在系统设置调整。多文件 SET / BrainVision 暂未开放。`, `Up to ${preferences.max_upload_mb} MB per file; change in System settings. Multi-file SET / BrainVision is not available yet.`)}</p>
          <button className="primary full" disabled={!file || busy} onClick={() => submit()}>{busy ? t("正在预检…", "Checking…") : t("开始清洗", "Start cleaning")} →</button>
        </div><div className="card"><div className="section-title"><span className="number">02</span><h2>{t("处理参数", "Processing settings")}</h2></div>
          <div className="fields"><label>{t("高通 Hz", "High-pass Hz")}<input type="number" min="0" step="0.1" value={low} onChange={e => setLow(Number(e.target.value))}/></label><label>{t("低通 Hz", "Low-pass Hz")}<input type="number" min="1" value={high} onChange={e => setHigh(Number(e.target.value))}/></label><label>{t("工频 Hz", "Line frequency Hz")}<select value={notch} onChange={e => setNotch(Number(e.target.value))}><option>50</option><option>60</option></select></label></div>
          <label className="check"><input type="checkbox" checked={asr} onChange={e => setAsr(e.target.checked)}/>ASR · {t("瞬态伪迹处理", "Transient artifact correction")}</label>
          <label className="check"><input type="checkbox" checked={ica} onChange={e => setIca(e.target.checked)}/>ICA / ICLabel · {t("成分识别", "Component classification")}</label>
          <label className="check"><input type="checkbox" checked={pdf} onChange={e => setPdf(e.target.checked)}/>{t("额外生成 PDF 分析报告", "Also generate a PDF analysis report")}</label>
          <p className="muted">{t("默认导出 FIF、EDF、CSV 和离线 HTML 报告。报告语言使用系统设置。", "Exports FIF, EDF, CSV and an offline HTML report. Report language follows System settings.")}</p>
        </div></section>
</>}
      {tab === "samples" && <><section className="sample-grid">{demos.map((d,i)=><article className="card sample-card" key={d.id}><span className="number">0{i+1} / {d.filename.split(".").pop()?.toUpperCase()}</span><h2>{en?d.name_en:d.name}</h2><p>{[t("64 通道 · 160 Hz · 61 秒。适合第一次体验完整清洗与报告流程。","64 channels · 160 Hz · 61 seconds. A quick introduction to cleaning and reports."),t("64 通道 · 160 Hz · 125 秒。用于查看运动想象记录的处理结果。","64 channels · 160 Hz · 125 seconds. Explore processing of motor imagery recordings."),t("25 通道 · 250 Hz · 约 45 分钟。较大样例，处理需要更长时间。","25 channels · 250 Hz · about 45 minutes. This larger sample takes longer to process.")][i]}</p><code>{d.filename}</code><button className="primary full" disabled={busy || !d.available} onClick={()=>submit(d.id)}>{d.available ? (busy?t("提交中…","Submitting…"):t("运行样例","Run sample")) : t("样例未下载","Sample not downloaded")} →</button></article>)}</section><div className="card"><h2>{t("本次样例使用的参数","Current sample settings")}</h2><p>{low}–{high} Hz · {notch} Hz · ASR {asr?"ON":"OFF"} · ICA {ica?"ON":"OFF"} · {lang.toUpperCase()} · HTML{pdf?" + PDF":""}</p><button className="secondary" onClick={()=>setTab("clean")}>{t("调整处理参数","Adjust settings")}</button><p className="muted">{t("缺失样例请按 backend/test_data/README.md 下载。运行后会显示进度并自动打开报告。","For missing samples, follow backend/test_data/README.md. Running a sample opens progress and then its report.")}</p></div></>}
      {tab === "history" && <section className="card"><div className="history-tools"><input aria-label={t("搜索文件名","Search filename")} placeholder={t("搜索文件名…","Search filename…")} value={query} onChange={e=>setQuery(e.target.value)}/><select aria-label={t("任务状态","Job status")} value={filter} onChange={e=>setFilter(e.target.value)}>{["all","completed","running","queued","failed"].map(x=><option value={x} key={x}>{x==="all"?t("全部状态","All statuses"):status({status:x} as Job)}</option>)}</select><button className="primary" onClick={()=>setTab("clean")}>{t("新建清洗任务","New cleaning job")}</button></div>{!loaded ? <p>{t("正在读取历史…","Loading history…")}</p> : history(jobs.filter(j=>j.filename.toLowerCase().includes(query.toLowerCase()) && (filter==="all" || j.status===filter)))}</section>}
      {["jobs","reports"].includes(tab) && (!current ? <div className="card">{loaded?t("未找到此任务，请返回历史记录选择。","Job not found. Select a job from history."):t("正在读取任务…","Loading job…")}<button className="secondary" onClick={()=>setTab("history")}>{names.history}</button></div> : <>
        <section className="card"><div className="section-title"><div className="job-title"><h2>{current.filename}</h2><p className="muted">{date(current)} · {current.dataset.n_channels} {t("通道","channels")} · {current.dataset.sfreq} Hz · {current.dataset.duration.toFixed(1)} s</p></div><span className={`badge ${current.status}`}>{status(current)}</span><button className="secondary" onClick={()=>setTab("history")}>{t("返回历史","Back to history")}</button></div>
        {current.status !== "completed" && <><progress aria-label={t("清洗进度","Cleaning progress")} value={current.progress} max="100"/><p aria-live="polite">{status(current)} · {current.progress}% · {current.step}</p><p>{t("处理完成后会自动进入报告查看页面。","The report opens automatically when processing finishes.")}</p></>}
        {current.error && <p className="error-text" role="alert">{current.error}</p>}{current.warnings.map((w,i)=><p key={i} className="warning">{w}</p>)}
        {current.metrics && <div className="score">{String(current.metrics.quality_score ?? "—")}<small>/ 100 · {t("数据质量评分","Data quality score")}</small></div>}
        {downloads(current)}{current.status === "completed" && <ReportExports key={current.id} job={current} en={en} onUpdate={()=>{api<Job[]>("/jobs").then(setJobs).catch(e=>setError(e.message));}}/>}{current.status === "completed" && tab === "jobs" && <a className="primary" href={`#/reports/${current.id}`}>{t("查看完整报告", "View full report")}</a>}{current.status === "completed" && <button className="secondary" onClick={()=>{setSelected(current.id);setTab("ai");}}>{t("向 AI 提问","Ask AI")} →</button>}</section>
        {current.status === "completed" && tab === "reports" && (current.outputs.html ? <section className="report-panel"><div className="section-title"><h2>{t("完整分析报告","Full analysis report")}</h2><a className="secondary" href={`/api/jobs/${current.id}/report`} target="_blank" rel="noreferrer">{t("新窗口全宽查看","Open full-width report")} ↗</a></div><iframe key={current.id} title={t("脑电分析报告","EEG analysis report")} src={`/api/jobs/${current.id}/report`} sandbox="allow-scripts allow-downloads"/></section> : <div className="warning">{t("此任务没有生成 HTML 报告，请查看上述警告和可下载结果。","No HTML report was generated for this job. Review warnings and available outputs above.")}</div>)}
        <details className="card"><summary>{t("处理参数与步骤记录","Parameters & processing log")}</summary><pre>{JSON.stringify({parameters:current.config,steps:current.steps},null,2)}</pre></details>
      </>)}
      {tab === "help" && <HelpCenter en={en}/>}
      {tab === "copyright" && <HelpCenter en={en} legal/>}
      {preferencesLoaded && <div hidden={tab !== "settings"}><SystemSettings en={en} value={preferences} onChange={value=>{setPreferences(value);setPdf(value.default_pdf);}}/></div>}
      {tab === "settings" && !preferencesLoaded && <p>{t("正在读取设置…", "Loading settings…")}</p>}
      <div hidden={tab !== "ai"}><ReportAssistant en={en} initialJobId={selected}/></div>
      <footer><div className="footer-links"><a href="#/help">{t("使用文档", "User guide")}</a><a href="#/copyright">{t("版权与非商业许可", "Copyright & noncommercial license")}</a></div><p>{languageMode === "auto" ? (languageSource === "ip" ? t("语言根据公网 IP 地区自动选择，可手动切换。", "Language follows your public IP region. You can change it manually.") : t("IP 地区暂不可用，已使用浏览器语言。", "IP location is unavailable; using your browser language.")) : t("已使用手动选择的语言。", "Using your selected language.")}{" "}{t("自动模式通过 ipwho.is 查询出口地区。", "Auto mode checks your exit region via ipwho.is.")}</p>{t("Brainifly Local · 用于科研数据预处理。质量评分及 AI 解释不构成医疗诊断。","Brainifly Local · Research preprocessing. Scores and AI explanations are not medical diagnoses.")}</footer>
    </main>
  </div>;
}
ReactDOM.createRoot(document.getElementById("root")!).render(<React.StrictMode><App/></React.StrictMode>);
