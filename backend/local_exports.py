"""Offline exports from saved results. Never reruns the cleaning pipeline."""
from dataclasses import asdict
from datetime import datetime, timezone
from html import escape
from io import BytesIO
import json
from pathlib import Path
import zipfile

from config import PipelineConfig
from core.loader import EEGLoader
from core.pipeline import PipelineResult
from core.quality import QualityMetrics
from core.steps.base import StepResult
from report.static_figures import MatplotlibFigureFactory, STATIC_STYLE_DEFINITIONS

FIGURES = {
    'quality_gauge': ('quality_gauge', '数据质量评分', 'Data quality score'),
    'psd_comparison': ('psd_comparison', '功率谱对比', 'Power spectral density comparison'),
    'waveform_comparison': ('waveform_comparison', '波形对比', 'Waveform comparison'),
    'channel_std': ('channel_std_comparison', '通道标准差', 'Channel standard deviation'),
    'band_power': ('band_power_comparison', '频段功率', 'Band power'),
    'topomap_comparison': ('topomap_comparison', '头皮分布对比', 'Scalp topography comparison'),
    'step_timeline': ('step_timeline', '处理步骤耗时', 'Processing step duration'),
}
REBUILD_NOTE = ('Reconstructed from saved original and cleaned recordings, parameters, metrics and step logs. '
                'Cleaning was not rerun. Historical ICA objects are not retained; component maps are not recreated. '
                'Scalp locations may use the plotting factory\'s standard montage fallback. '
                'Inspect labels, warnings and channel positions before publication. Scores are not diagnoses.')


def saved_file(directory, relative):
    path = (directory / relative).resolve()
    if not path.is_relative_to(directory.resolve()) or not path.is_file():
        raise ValueError('Required saved recording is missing or outside the job folder.')
    return path


def restore_result(directory, job):
    config = PipelineConfig.model_validate(job['config'])
    source = saved_file(directory, 'input' + Path(job['filename']).suffix.lower())
    cleaned = None
    for kind in ('fif', 'edf'):
        if kind in job['outputs']:
            try:
                cleaned = saved_file(directory, job['outputs'][kind])
                break
            except ValueError:
                continue
    if cleaned is None:
        raise ValueError('No saved FIF/EDF result is available. This job cannot be exported.')
    before = EEGLoader.load(source, input_adapter=config.input_adapter)
    after = None
    try:
        after = EEGLoader.load(cleaned)
        info = EEGLoader.extract_metadata(before, source)
        info.filename = job['filename']
        info.filepath = info.filename
        steps = [StepResult(**{k: v for k, v in step.items() if k in StepResult.__dataclass_fields__}) for step in job.get('steps', [])]
        if not isinstance(job.get('metrics'), dict):
            raise ValueError('Saved quality metrics are missing; export cannot reconstruct them reliably.')
        metrics = QualityMetrics(**{k: v for k, v in job['metrics'].items() if k in QualityMetrics.__dataclass_fields__})
        return PipelineResult(raw_before=before, raw_after=after, dataset_info=info,
                              step_results=steps, metrics=metrics, config=config,
                              total_duration=sum(step.duration for step in steps), context={})
    except Exception:
        before.close()
        if after is not None:
            after.close()
        raise


def render_figures(result, style):
    factory = MatplotlibFigureFactory(result.raw_before, result.raw_after, result.step_results, result.context, result.metrics)
    for name, (method, _, _) in FIGURES.items():
        figure = None
        try:
            figure = getattr(factory, method)(style_code=style)
            texts = [text.get_text() for ax in figure.axes for text in ax.texts]
            placeholder = [text for text in texts if any(word in text.lower() for word in ('insufficient', 'requires at least', 'no step', 'no channels', 'not available', 'unavailable'))]
            yield name, figure, placeholder
        except Exception as exc:
            yield name, None, [f'{type(exc).__name__}: {exc}']
        finally:
            if figure is not None:
                import matplotlib.pyplot as plt
                plt.close(figure)


def research_bundle(result, output, progress=lambda message: None):
    manifest = {'generated_at': datetime.now(timezone.utc).isoformat(), 'filename': result.dataset_info.filename,
                'renderer': 'Matplotlib', 'png_dpi': 300, 'formats': ['png', 'svg', 'pdf'],
                'notes': [REBUILD_NOTE], 'figures': {}}
    warnings = []
    count = 0
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as bundle:
        def put_json(name, value):
            bundle.writestr(name, json.dumps(value, ensure_ascii=False, indent=2, default=str))
        put_json('parameters.json', result.config.model_dump(mode='json'))
        dataset = asdict(result.dataset_info)
        dataset.pop('filepath', None)
        put_json('dataset_info.json', dataset)
        put_json('quality_metrics.json', asdict(result.metrics))
        put_json('processing_steps.json', [asdict(step) for step in result.step_results])
        for style in STATIC_STYLE_DEFINITIONS:
            manifest['figures'][style] = {}
            for name, figure, issues in render_figures(result, style):
                progress(f'{style} / {name}')
                entry = {'files': [], 'warnings': list(issues)}
                if figure is not None:
                    for fmt in ('png', 'svg', 'pdf'):
                        try:
                            buffer = BytesIO()
                            figure.savefig(buffer, format=fmt, dpi=300, bbox_inches='tight')
                            path = f'figures/{style}/{name}.{fmt}'
                            bundle.writestr(path, buffer.getvalue())
                            entry['files'].append(path)
                            count += 1
                        except Exception as exc:
                            entry['warnings'].append(f'{fmt}: {type(exc).__name__}: {exc}')
                warnings.extend(f'{style}/{name}: {warning}' for warning in entry['warnings'])
                manifest['figures'][style][name] = entry
        if not count:
            raise ValueError('No research figures could be rendered.')
        bundle.writestr('README.md', '# OpenBrainEEG research figures / 科研图包\n\n'
            'Three styles: academic_bw (黑白), standard_color (彩色), presentation (演示).\n'
            'PNG: 300 dpi. SVG and PDF: vector containers; raster artists, if any, remain raster.\n'
            'Figures use English labels. Check journal dimensions, fonts and resolution requirements.\n\n'
            + REBUILD_NOTE + '\n\n原始数据及清洗结果未包含在本包中。历史任务重绘，不重新清洗；不恢复历史 ICA 成分对象。'
            '缺少通道坐标时可能使用标准模板或生成说明占位图，不能视为实际测量位置。'
            '请复核图、参数和步骤警告，不要直接将质量评分当作科研或临床结论。\n'
            'Inspect manifest.json for missing figures, partial exports and placeholder warnings.\n')
        put_json('manifest.json', manifest)
    return warnings


def pdf_report(result, output, progress=lambda message: None, *, reconstructed=True):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, Image
    # Standard CJK PDF font. No proprietary font file is redistributed.
    if 'STSong-Light' not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(UnicodeCIDFont('STSong-Light'))
    en = result.config.report_language == 'en'
    t = lambda zh, english: english if en else zh
    font = 'STSong-Light'
    body = ParagraphStyle('body', fontName=font, fontSize=10, leading=16, spaceAfter=8, wordWrap='CJK', textColor=colors.HexColor('#18283f'))
    heading = ParagraphStyle('heading', parent=body, fontSize=18, leading=26, spaceAfter=14)
    small = ParagraphStyle('small', parent=body, fontSize=8, leading=12)
    p = lambda text, style=body: Paragraph(escape(str(text)).replace('\n', '<br/>'), style)
    story = [p(t('脑电数据分析报告', 'EEG data analysis report'), heading),
             p('OpenBrainEEG / Brainifly Local'), p(result.dataset_info.filename),
             p(t('本报告用于科研辅助，需独立复核。质量评分不代表脑健康，不构成诊断或治疗建议。',
                 'Research assistance only. Review independently. Quality scores do not describe brain health or provide diagnosis or treatment.'))]
    width = A4[0] - 88
    def table(rows):
        cells = [[p(cell) for cell in row] for row in rows]
        item = Table(cells, colWidths=[width * .42, width * .58], hAlign='LEFT', repeatRows=0)
        item.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'TOP'), ('BACKGROUND', (0,0), (0,-1), colors.HexColor('#edf3ff')),
                                 ('LINEBELOW', (0,0), (-1,-1), .4, colors.HexColor('#dce3ed')),
                                 ('LEFTPADDING',(0,0),(-1,-1),8),('TOPPADDING',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),7)]))
        return item
    info, metrics = result.dataset_info, result.metrics
    story += [table([(t('通道 / 采样率', 'Channels / sample rate'), f'{info.n_channels} / {info.sfreq:g} Hz'),
                     (t('记录时长', 'Duration'), f'{info.duration:.2f} s'),
                     (t('质量评分 / 等级', 'Quality score / grade'), f'{metrics.quality_score} / 100 · {metrics.quality_grade}'),
                     (t('信噪比：清洗前 / 后', 'SNR: before / after'), f'{metrics.snr_before:.2f} / {metrics.snr_after:.2f} dB'),
                     (t('坏导数 / 占比', 'Bad channels / ratio'), f'{metrics.n_bad_channels} / {metrics.bad_channel_ratio:.1%}'),
                     (t('ICA 排除 / 总数', 'ICA excluded / total'), f'{metrics.n_ica_excluded} / {metrics.n_ica_components}'),
                     (t('原处理耗时', 'Original processing duration'), f'{result.total_duration:.2f} s')]), Spacer(1,14)]
    if reconstructed:
        story += [p(t('根据保存的原始记录、清洗结果、参数、指标和步骤日志重绘；未重新清洗。历史 ICA 成分对象未保存，报告不恢复成分图。', REBUILD_NOTE), small)]
    warnings = [f'{step.step_name}: {w}' for step in result.step_results for w in step.warnings]
    story += [p(t('处理警告', 'Processing warnings'), heading)]
    story += [p(w) for w in warnings] or [p(t('未记录步骤警告；这不保证结果正确。', 'No step warnings recorded; this does not guarantee correctness.'))]
    export_warnings = []
    for name, figure, issues in render_figures(result, 'standard_color'):
        progress(name)
        story += [PageBreak(), p(FIGURES[name][2 if en else 1], heading)]
        export_warnings.extend(f'{name}: {issue}' for issue in issues)
        if figure is not None:
            data = BytesIO()
            figure.savefig(data, format='png', dpi=180, bbox_inches='tight')
            data.seek(0)
            img = Image(data)
            ratio = min(width/img.imageWidth, 550/img.imageHeight)
            img.drawWidth = img.imageWidth*ratio
            img.drawHeight = img.imageHeight*ratio
            story += [img, Spacer(1,12)]
        story += [p(issue) for issue in issues]
        story += [p(t('图表沿用原报告绘图算法，图内使用英文标注。头皮图可能使用标准电极模板；缺少位置时显示说明，发表前应核对通道位置。',
                       'Figures use the existing report plotting algorithms and English labels. Scalp maps may use a standard electrode montage; missing positions produce a notice. Verify positions before publication.'), small)]
    story += [PageBreak(), p(t('处理步骤与指标', 'Processing steps and metrics'), heading)]
    for step in result.step_results:
        story += [p(f'{step.step_name} · {step.duration:.2f} s'), p(step.description), p(json.dumps(step.metrics, ensure_ascii=False, default=str), small)]
    story += [p(t('完整质量指标', 'Full quality metrics'), heading)]
    story += [table([(k, json.dumps(v, ensure_ascii=False, default=str)) for k,v in asdict(metrics).items()])]
    story += [PageBreak(), p(t('处理参数', 'Processing parameters'), heading)]
    for line in result.config.model_dump_json(indent=2).splitlines():
        story += [p(line, small)]
    def footer(canvas, document):
        canvas.setFont(font,8)
        canvas.setFillColor(colors.HexColor('#596a80'))
        canvas.drawString(44,26,'OpenBrainEEG · Research assistance only')
        canvas.drawRightString(A4[0]-44,26,str(document.page))
    doc = SimpleDocTemplate(str(output), pagesize=A4, rightMargin=44, leftMargin=44, topMargin=40, bottomMargin=44,
                            title='OpenBrainEEG EEG report', author='OpenBrainEEG')
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return export_warnings
