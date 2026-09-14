import { useState } from 'react';
import guide from '../content/guide.json';
import license from '../../../LICENSE.md?raw';
import notices from '../../../LICENSING.md?raw';
import './HelpCenter.css';

function LegalText({ text }: { text: string }) {
  // Local, trusted Markdown only; React escapes text and no raw HTML is rendered.
  return <div className="legal-text">{text.trim().split(/\n\s*\n/).map((block, i) => {
    if (block.startsWith('#')) return <h3 key={i}>{block.replace(/^#{1,3}\s/gm, '').replace(/\n/g, ' · ')}</h3>;
    if (block.startsWith('- ')) return <ul key={i}>{block.split(/\n(?=- )/).map((line, j) => <li key={j}>{line.slice(2)}</li>)}</ul>;
    return <p key={i}>{block.split(/(\[[^\]]+\]\([^)]+\))/g).map((part, j) => {
      const link = /^\[([^\]]+)\]\((LICENSE\.md|LICENSING\.md)\)$/.exec(part);
      return link ? <a key={j} href={'/guide/' + link[2]} download>{link[1]}</a> : part;
    })}</p>;
  })}</div>;
}

export default function HelpCenter({ en, legal = false }: { en: boolean; legal?: boolean }) {
  const lang = en ? 'en' : 'zh';
  const t = (zh: string, english: string) => en ? english : zh;
  const [query, setQuery] = useState('');
  const sections = guide.filter(s => [s.title[lang], s.intro[lang], ...s.steps[lang], s.note[lang]].join(' ').toLowerCase().includes(query.trim().toLowerCase()));
  if (legal) return <div className="help-legal">
    <section className="card help-overview"><div className="help-owner"><p>{t('版权主体 · 母公司', 'Copyright holder · Parent company')}</p><h2>{t("元神认知（深圳）有限责任公司", "Origin Cognition (Shenzhen) Co., Ltd.")}</h2><p>{t("Origin Cognition (Shenzhen) Co., Ltd.", "元神认知（深圳）有限责任公司")}</p><p>Copyright © 2026 {t('元神认知（深圳）有限责任公司', 'Origin Cognition (Shenzhen) Co., Ltd.')}</p></div><h2>{t('个人非商业使用免费，商业使用需书面授权', 'Free for personal noncommercial use; commercial use requires written authorization')}</h2>
      <p>{t('可以学习、运行、修改及按相同条款免费分享本项目有权许可的原创代码。不得未经授权用于公司业务、收费服务、产品集成或其他商业用途。', 'You may study, run, modify and share eligible original code free of charge under the same terms. Company operations, paid services, product integration and other commercial uses need authorization.')}</p>
      <p>{t('这是非商业源码许可，不是 OSI 定义的开源许可。第三方库、模型和公开样例保留各自许可。', 'This is a noncommercial source-available license, not an OSI open-source license. Third-party libraries, models and public samples retain their own terms.')}</p>
      <div className="help-caution"><strong>{t('请独立复核分析结果', 'Independently review results')}</strong><p>{t('软件、算法、质量评分及 AI 回答可能出错，仅供研究辅助，不构成诊断或治疗建议。在适用法律允许的最大范围内按现状提供，不保证正确性或特定用途适用性；依法不能排除的责任不予排除。完整条款如下。', 'Software, algorithms, scores and AI answers may be wrong. They support research, not diagnosis or treatment. To the maximum extent permitted by applicable law, the software is provided as is, without guarantees of correctness or fitness. Liabilities that cannot legally be excluded remain unaffected. Full terms follow.')}</p></div>
      <div className="actions"><a className="secondary" href="/guide/LICENSE.md" download>{t('下载完整许可', 'Download full license')}</a><a className="secondary" href="/guide/LICENSING.md" download>{t('下载第三方说明', 'Download third-party notices')}</a></div>
    </section>
    <section className="card"><h2>{t('完整许可条款', 'Full license terms')}</h2><p className="muted">OpenBrainEEG Personal Noncommercial License 1.0 · 2026-09-14</p><LegalText text={en ? license.split('## English translation')[1] : license.split('## 中文条款（主文本）')[1].split('## English translation')[0]}/></section>
    <section className="card"><h2>{t('第三方与权属说明', 'Third-party and ownership notices')}</h2><LegalText text={notices}/></section>
  </div>;
  return <div className="help-layout">
    <nav className="help-index" aria-label={t('使用手册目录', 'User guide contents')}>
      <label htmlFor="guide-search">{t('搜索手册', 'Search guide')}</label><input id="guide-search" type="search" value={query} onChange={e => setQuery(e.target.value)} placeholder={t('例如：报告、DeepSeek', 'e.g. reports, DeepSeek')}/>
      {sections.map(s => <button key={s.id} onClick={() => { const target = document.getElementById('guide-' + s.id); target?.scrollIntoView({ block: 'start' }); target?.focus({ preventScroll: true }); }}>{s.title[lang]}</button>)}
      <a href={`/guide/USER_GUIDE.${en ? 'en' : 'zh-CN'}.md`} download>{t('下载 Markdown 手册', 'Download Markdown guide')}</a>
      <a href="/guide/OpenBrainEEG-user-guide.zip" download>{t('下载离线图文包', 'Download illustrated offline guide')}</a>
      <a href={`/guide/USER_GUIDE.${en ? 'en' : 'zh-CN'}.html`} target="_blank" rel="noreferrer">{t('独立阅读 / 打印', 'Read separately / print')}</a>
      <a href="#/copyright">{t('版权与使用许可', 'Copyright and license')}</a>
    </nav>
    <div className="help-body"><section className="help-intro"><h2>{t('从第一个样例到一份可复核的报告', 'From your first sample to a reviewable report')}</h2><p>{t('按实际界面逐步操作。无需配置 AI，也可以完成清洗与报告查看。点击截图可打开原图。', 'Follow the real interface step by step. Cleaning and reports work without AI. Select a screenshot to open the full image.')}</p><p className="muted">{t('截图使用公开 PhysioNet 样例和独立演示工作区；不含私人数据或真实密钥。', 'Screenshots use public PhysioNet samples in an isolated demo workspace, with no private data or real keys.')}</p></section>
      {sections.length === 0 && <p role="status">{t('未找到匹配章节，请换个关键词。', 'No matching sections. Try another keyword.')}</p>}
      {sections.map(s => <section className="help-section" id={'guide-' + s.id} key={s.id} tabIndex={-1}>
        <h2>{s.title[lang]}</h2><p>{s.intro[lang]}</p>
        {s.code && <pre className="help-code"><code>{s.code}</code></pre>}
        <ol>{s.steps[lang].map(step => <li key={step}>{step}</li>)}</ol>
        {s.image && <figure><a href={`/guide/${s.image}-${lang}.png`} target="_blank" rel="noreferrer" aria-label={t('放大截图：', 'Enlarge screenshot: ') + s.title[lang]}><img src={`/guide/${s.image}-${lang}.png`} alt={t('实际界面：', 'Actual interface: ') + s.title[lang]} loading="lazy" width="1980" height="1280"/></a><figcaption>{s.title[lang]} · {t('点击查看原图', 'Select to view full size')}</figcaption></figure>}
        {s.note[lang] && <div className="help-caution">{s.note[lang]}</div>}
        {s.links.length > 0 && <p className="help-sources">{s.links.map(link => <a key={link.url} href={link.url} target="_blank" rel="noreferrer">{link.label}</a>)}</p>}
      </section>)}
    </div>
  </div>;
}
