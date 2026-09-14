"""Generate bilingual Markdown, offline HTML and a ZIP from the in-app guide.

Run after updating guide.json, LICENSE.md or screenshots. Does not capture a
browser, run AI, or read .local-data. Uses only Python's standard library.
"""
from pathlib import Path
from html import escape
import json
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / 'frontend/public/guide'


def main():
    sections = json.loads((ROOT / 'frontend/src/content/guide.json').read_text(encoding='utf-8'))
    PUBLIC.mkdir(exist_ok=True)
    files = []
    for section in sections:
        if section['image']:
            for language in ('zh', 'en'):
                path = PUBLIC / f"{section['image']}-{language}.png"
                if not path.is_file():
                    raise FileNotFoundError(f'Capture the actual UI screenshot first: {path}')
                files.append(path)
    for name in ('LICENSE.md', 'LICENSING.md'):
        (PUBLIC / name).write_bytes((ROOT / name).read_bytes())
        files.append(PUBLIC / name)
    style = """body{font:20px/1.8 'Segoe UI','Microsoft YaHei',sans-serif;color:#18283f;background:#f5f7fb;margin:0}main{width:100%;box-sizing:border-box;margin:auto;padding:40px clamp(20px,4vw,80px)}a{color:#245bd8}h1,h2{line-height:1.35}section{border-top:1px solid #dce3ed;padding:28px 0}li{margin:12px 0}img{max-width:100%;height:auto;border:1px solid #dce3ed}pre{overflow:auto;padding:20px;background:white}blockquote{border-left:3px solid #245bd8;padding:12px 20px;background:#edf3ff;margin:20px 0}nav a{display:inline-block;margin:4px 20px 4px 0}@media(max-width:700px){body{font-size:16px}}@media print{section{break-inside:avoid}body{background:white}}"""
    for lang, suffix, title in [('zh', 'zh-CN', '使用手册'), ('en', 'en', 'User guide')]:
        intro = ('配图来自独立演示工作区的真实界面，使用公开 PhysioNet 样例，不含私人录波、真实 API Key 或 AI 生成结论。设置截图展示未保存的 DeepSeek 预设，未发起 AI 调用。英文界面的报告截图保留样例任务提交时的中文报告。' if lang == 'zh' else 'Screenshots show a real isolated workspace using public PhysioNet samples. They contain no private recordings, real API keys or generated AI conclusions. Settings show an unsaved DeepSeek preset; no AI request was sent. The English-interface report screenshot retains the Chinese report language selected when the sample job was submitted.')
        md = [f'# OpenBrainEEG {title}', '', 'Brainifly Local · 2026-09-14', '', intro, '']
        html = [f'<!doctype html><html lang="{suffix}"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>OpenBrainEEG {title}</title><style>{style}</style><main><h1>OpenBrainEEG {title}</h1><p>Brainifly Local · 2026-09-14</p><p>{intro}</p><nav aria-label="Contents">']
        html += [f'<a href="#{s["id"]}">{escape(s["title"][lang])}</a>' for s in sections]
        html += ['</nav>']
        for s in sections:
            md += ['## '+s['title'][lang], '', s['intro'][lang], '']
            html += [f'<section id="{s["id"]}"><h2>{escape(s["title"][lang])}</h2><p>{escape(s["intro"][lang])}</p>']
            if s['code']:
                md += ['```text', s['code'], '```', '']
                html += [f'<pre><code>{escape(s["code"])}</code></pre>']
            md += [f'{i}. {step}' for i, step in enumerate(s['steps'][lang], 1)] + ['']
            html += ['<ol>'] + ['<li>'+escape(step)+'</li>' for step in s['steps'][lang]] + ['</ol>']
            if s['image']:
                name = f'{s["image"]}-{lang}.png'
                md += [f'![{s["title"][lang]}]({name})', '']
                html += [f'<a href="{name}"><img loading="lazy" src="{name}" alt="{escape(s["title"][lang])}"></a>']
            if s['note'][lang]:
                md += ['> '+s['note'][lang], '']
                html += ['<blockquote>'+escape(s['note'][lang])+'</blockquote>']
            for link in s['links']:
                md += [f'[{link["label"]}]({link["url"]})', '']
                html += [f'<p><a href="{escape(link["url"])}">{escape(link["label"])}</a></p>']
            html += ['</section>']
        md += ['[License / 许可](LICENSE.md) · [Third-party notices / 第三方说明](LICENSING.md)', '']
        html += ['<footer><a href="LICENSE.md">License / 许可</a> · <a href="LICENSING.md">Third-party notices / 第三方说明</a></footer></main></html>']
        text = '\n'.join(md)
        name = f'USER_GUIDE.{suffix}.md'
        (PUBLIC / name).write_text(text, encoding='utf-8')
        files.append(PUBLIC / name)
        repo_text = text.replace('](LICENSE.md)', '](../LICENSE.md)').replace('](LICENSING.md)', '](../LICENSING.md)')
        for s in sections:
            if s['image']:
                image = f'{s["image"]}-{lang}.png'
                repo_text = repo_text.replace(f']({image})', f'](../frontend/public/guide/{image})')
        (ROOT / 'docs' / name).write_text(repo_text, encoding='utf-8')
        page = PUBLIC / f'USER_GUIDE.{suffix}.html'
        page.write_text('\n'.join(html), encoding='utf-8')
        files.append(page)
    archive = PUBLIC / 'OpenBrainEEG-user-guide.zip'
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as bundle:
        for file in sorted(set(files)):
            bundle.write(file, 'OpenBrainEEG-user-guide/' + file.name)
    print(f'Exported two languages and {len(set(files))} offline files: {archive.name}')


if __name__ == '__main__':
    main()
