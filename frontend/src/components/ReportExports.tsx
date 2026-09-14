import { useState } from 'react';
import { api } from '../api';
export type ExportState = {status:string;step?:string;error?:string|null;warnings?:string[]};
export type ExportJob = {id:string;outputs:Record<string,string>;exports?:Record<string,ExportState>};

export default function ReportExports({job,en,onUpdate}:{job:ExportJob;en:boolean;onUpdate:()=>void}) {
  const t=(zh:string,english:string)=>en?english:zh;
  const [sending,setSending]=useState('');
  const [error,setError]=useState('');
  const [pending,setPending]=useState<Record<string,ExportState>>({});
  async function generate(kind:string) {
    setSending(kind);setError('');
    try {
      const result=await api<ExportJob>(`/jobs/${job.id}/exports/${kind}`,{method:'POST'});
      setPending(result.exports || {});onUpdate();
    } catch(e){setError((e as Error).message);}finally{setSending('');}
  }
  return <section className="report-exports" aria-label={t('报告与科研图导出','Report and research figure exports')}>
    <h3>{t('报告与科研图导出','Report and research figure exports')}</h3>
    <div className="export-grid">{(['pdf','research_figures'] as const).map(kind=>{
      const state=job.exports?.[kind] || pending[kind];
      const active=state?.status==='queued'||state?.status==='running';
      const available=!!job.outputs[kind];
      return <article key={kind} className="export-option">
        <h4>{kind==='pdf'?t('PDF 分析报告','PDF analysis report'):t('科研图包','Research figure bundle')}</h4>
        <p>{kind==='pdf'?t('可离线阅读和打印，包含指标、警告、图表及处理参数。','Read and print offline, with metrics, warnings, figures and processing parameters.'):t('三种样式 · 300 dpi PNG / SVG / 单图 PDF，以及参数、指标和导出清单。','Three styles · 300 dpi PNG / SVG / individual PDFs, plus parameters, metrics and a manifest.')}</p>
        {available?<a className="primary" href={`/api/jobs/${job.id}/files/${kind}`} download>{kind==='pdf'?t('下载 PDF 报告','Download PDF report'):t('下载科研图 ZIP','Download figure ZIP')}</a>:<button className="secondary" disabled={active||!!sending} onClick={()=>generate(kind)}>{active?(state.status==='queued'?t('已排队，等待生成…','Queued for export…'):t('正在生成…','Generating…')):sending===kind?t('正在提交…','Submitting…'):state?.status==='failed'?t('重新生成','Retry export'):kind==='pdf'?t('生成 PDF 报告','Generate PDF report'):t('生成科研图包','Generate figure bundle')}</button>}
        {active&&<p role="status" className="muted">{t('与清洗任务共用队列，离开页面后仍继续处理。','Shares the cleaning queue and continues if you leave this page.')} {state.step && state.step!=='waiting' && state.step!=='loading' && state.step}</p>}
        {state?.status==='failed'&&<p className="error-text" role="alert">{state.error}</p>}
        {!!state?.warnings?.length&&<details><summary>{t(`${state.warnings.length} 条导出提示，请查看`,`${state.warnings.length} export notices — review before use`)}</summary>{state.warnings.map((w,i)=><p key={i}>{w}</p>)}</details>}
      </article>;
    })}</div>
    <p className="muted">{t('历史任务使用已保存的结果重绘，不会重新清洗；需保留原始输入和 FIF/EDF 输出。ICA 成分对象未保存，不补造历史成分图。科研图内采用英文标注，发表前请复核通道位置与期刊要求。','Historical exports redraw saved results without rerunning cleaning. Keep the original input and FIF/EDF output. Historical ICA objects are not retained, so component maps are not recreated. Figures use English labels; review electrode positions and journal requirements before publication.')}</p>
    {error&&<p role="alert" className="error-text">{error}</p>}
  </section>;
}
