import { useState } from "react";
import { api, json } from "../api";
import AIConnection from "./AIConnection";
export type Preferences = { max_upload_mb:number; max_active_jobs:number; report_language:"auto"|"zh"|"en"; default_pdf:boolean; auto_open_report:boolean };
export const defaultPreferences:Preferences = {max_upload_mb:512,max_active_jobs:4,report_language:"auto",default_pdf:false,auto_open_report:true};
export default function SystemSettings({en,value,onChange}:{en:boolean;value:Preferences;onChange:(value:Preferences)=>void}) {
  const t=(zh:string,enText:string)=>en?enText:zh;
  const [busy,setBusy]=useState(false),[error,setError]=useState(""),[notice,setNotice]=useState("");
  async function save(event:React.FormEvent<HTMLFormElement>){
    event.preventDefault();const data=new FormData(event.currentTarget);setBusy(true);setError("");setNotice("");
    try{const next=await api<Preferences>("/settings",json("PUT",{max_upload_mb:Number(data.get("size")),max_active_jobs:Number(data.get("queue")),report_language:data.get("language"),default_pdf:data.has("pdf"),auto_open_report:data.has("open")}));onChange(next);setNotice(t("系统设置已保存，新任务使用这些设置。","System settings saved. These apply to new jobs."));}
    catch(e){setError((e as Error).message);}finally{setBusy(false);}
  }
  return <div className="grid ai-grid"><AIConnection en={en}/><div><section className="card"><h2>{t("任务与报告", "Jobs & reports")}</h2>
    <form key={JSON.stringify(value)} onSubmit={save}><label>{t("单文件上传上限（MB）", "Upload limit per file (MB)")}<input required type="number" name="size" min={1} max={8192} defaultValue={value.max_upload_mb}/></label><p className="muted">{t("后端实际执行此限制。大文件清洗可能占用数倍内存，请按本机资源设置。", "Enforced by the backend. Processing may use several times the file size in memory.")}</p>
    <label>{t("运行与排队任务总数上限", "Maximum active and queued jobs")}<input required type="number" name="queue" min={1} max={16} defaultValue={value.max_active_jobs}/></label><p className="muted">{t("仍逐个执行清洗任务，避免多个任务同时争用内存。", "Cleaning jobs run one at a time to control memory use.")}</p>
    <label>{t("默认报告语言", "Default report language")}<select name="language" defaultValue={value.report_language}><option value="auto">{t("跟随界面", "Follow interface")}</option><option value="zh">中文</option><option value="en">English</option></select></label>
    <label className="check"><input name="pdf" type="checkbox" defaultChecked={value.default_pdf}/>{t("默认额外生成 PDF", "Generate PDF by default")}</label><p className="muted">{t("PDF 使用跨平台内置导出；也可在报告页按需生成。", "PDF uses the cross-platform exporter; you can also generate it from the report page.")}</p>
    <label className="check"><input name="open" type="checkbox" defaultChecked={value.auto_open_report}/>{t("清洗完成后自动打开报告", "Open report after cleaning")}</label>
    <button className="primary" disabled={busy}>{busy?t("保存中…", "Saving…"):t("保存任务设置", "Save job settings")}</button></form>
    {error&&<div className="alert error" role="alert">{error}</div>}{notice&&<div className="connection-status" role="status">{notice}</div>}</section>
    <section className="card"><h2>{t("本地工作区", "Local workspace")}</h2><p>{t("任务、报告、会话及设置保存在项目的 .local-data 目录。", "Jobs, reports, conversations and settings are stored in the project's .local-data directory.")}</p><p className="muted">{t("界面语言在右上角切换。模型只在读取模型列表、测试连接或主动提问时调用。", "Change interface language in the top right. AI services are contacted only when listing models, testing or asking questions.")}</p><a className="secondary" href="#/ai">{t("打开 AI 报告助手", "Open AI report assistant")}</a></section></div></div>;
}
