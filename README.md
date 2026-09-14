# OpenBrainEEG

**Local EEG cleaning, quality reports and configurable AI report discussions.**

[Download a release](https://github.com/ZhaoLiu-res/OpenBrainEEG/releases) · [What's new](CHANGELOG.md) · [Report a problem](https://github.com/ZhaoLiu-res/OpenBrainEEG/issues)

![Local EEG workspace](frontend/public/guide/home-en.png)

独立的本地脑电工作台，源自 Brainifly 详见www.brainifly.com 。本地版无需登录，支持中英文、Windows / macOS 启动、真实样例、数据清洗、历史报告和多轮 AI 解读。界面暂保留 Brainifly 品牌。

This repository contains only the standalone local edition, its automated tests,
and two attributed PhysioNet EDF examples. It does not include the original
hosted application's accounts, billing, cloud administration, private settings,
or repository history.

**License: personal noncommercial use.** Commercial and organizational use require written authorization. This is source-available software, not OSI open source. See [full license](LICENSE.md) and [third-party notices](LICENSING.md).

**使用手册 / User guide:** [中文图文手册](docs/USER_GUIDE.zh-CN.md) · [Illustrated English guide](docs/USER_GUIDE.en.md). 在系统侧栏打开「使用文档」或「版权信息」。

## 快速开始 / Quick start

安装 Python 3.11+ 和 Node.js 22。在项目根目录执行：

```powershell
python start.py setup
python start.py
```

macOS 使用所选 Python（例如 `python3.11`）替代 `python`：

```bash
python3.11 start.py setup
python3.11 start.py
```

打开 **http://127.0.0.1:8765**。首次 setup 安装独立依赖、构建前端并下载/校验一个 PhysioNet 样例；以后只需 start。端口不同于旧版的 8000/5173，可并存。关闭终端或 Ctrl+C 停止；正常退出会等待任务完成，强制关闭后未完成任务会标为中断失败，可重新提交。

Open **http://127.0.0.1:8765**. Setup installs dependencies, builds the UI and downloads/verifies one PhysioNet sample. Subsequent runs need only `python start.py`. No database, Redis, login or cloud account is needed.

## 页面与工作流程 / Pages & workflow

- 首页：介绍软件特点、处理流程和最近任务。
- 样例运行：三个真实样例入口，显示文件是否已下载；可前往清洗页调整参数。
- 数据清洗：上传录波、设置参数，提交后进入进度页；完成后自动进入报告页。
- 历史任务与报告：按文件名搜索、按状态筛选，重新打开报告、下载清洗数据和参数。
- 报告查看：内嵌完整原版 HTML 图表，支持新窗口全宽查看；保留质量评分、步骤警告和处理日志。
- AI 报告助手：保留本地/外部模型配置及主动提问流程。

Home → Samples or EEG cleaning → Job progress → Report viewer. History & reports keeps previous jobs searchable and accessible after restart. Use “Open full-width report” to view the complete report in a separate tab. AI remains optional.

页面使用哈希地址（例如 `#/history`、`#/reports/任务ID`），支持刷新和浏览器前进/后退。仅在当前任务进度页完成处理时自动跳转，浏览其他页面时不会被抢走。

工作台按可用窗口宽度伸展，已移除 1500 像素工作区和 1100 像素报告宽度上限，覆盖 1980×1280 与 2560×1440 布局目标；正文/控件以 16 像素为基准，并提供窄屏布局。浏览器缩放与系统显示缩放会改变 CSS 可用宽度；图文手册包含 1980×1280 实际浏览器截图；系统显示缩放仍以本机设置为准。

## 功能和范围 / Scope

- EDF / BDF / GDF / FIF / OpenBCI TXT / BrainFlow CSV 单文件上传，默认 512 MB，可在系统设置调整。
- 滤波、坏导处理、重参考、ASR、ICA/ICLabel；参数可调。
- FIF / EDF / CSV / 参数 JSON / 离线 HTML 报告下载，PDF 可选。
- 中文 / English 界面和报告；报告语言在提交时确定。
- 本地文件保存任务与结果，无每日额度；一次运行一个任务，默认最多 4 个排队/运行任务（系统设置可调整），避免单机资源失控。
- 没有用户、订阅、支付、管理平台、数据库迁移或在线账号功能。
- 本版暂不接收需要配套文件的 SET / BrainVision，也未迁入原版批量管理、分享链接、知识库。

Single-file inputs only. Multi-file SET/BrainVision, public sharing, cloud administration and batch management are not part of this initial edition. Computational limits protect the local machine; they are not paid quotas.

## 演示数据 / Samples

| 示例 | 文件 | 用途 |
| --- | --- | --- |
| 睁眼静息 / Eyes open | `physionet/S001R01.edf` | 默认快启样例，setup 会下载并核对 SHA256 |
| 左右手运动想象 / Motor imagery | `physionet/S001R04.edf` | 仓库已附带，按 SHA256 校验 |
| BCI Competition 训练 / Training | `bci_competition/A01T.gdf` | 不附带，需自行按数据源条款获取 |

路径位于 `backend/test_data`。仓库附带两个已校验的 PhysioNet EDF 样例及出处许可，GDF 不打包。见 [数据说明](backend/test_data/README.md)。

## 语言 / Language

右上角可选择「自动 / IP」「中文」「English」。自动模式通过本机后端向 `https://ipwho.is/?fields=success,country_code` 查询公网出口国家/地区：CN/HK/MO/TW 使用中文，其余使用英文。失败或离线时使用浏览器的中文/英文偏好。手动选择优先并保存在浏览器；手动模式不发起新的地区查询。

地区查询接口见 [IPWhois 文档](https://ipwhois.io/documentation)。地区服务会看到请求的公网 IP，不发送脑电记录、报告、问题或密钥。不保存 IP，仅在进程内缓存地区结果 24 小时，失败缓存 1 小时。VPN 出口或网络地区不能准确代表语言偏好，可随时手动切换。清洗功能不依赖查询成功。

Auto mode resolves the local server's public exit country through ipwho.is, then falls back to browser language if unavailable. Manual selection takes priority. No recordings, reports, questions or API keys are sent to the location service. VPNs may affect the inferred region. Offline EEG cleaning remains available.

## 系统设置与 AI / System settings & AI

「系统设置」集中管理上传大小、活动任务数量、默认报告语言/PDF、自动打开报告，以及本地/API AI 连接、超时、历史上下文和输出上限。

AI 支持 Ollama、LM Studio、vLLM/llama.cpp，以及 DeepSeek、Kimi、豆包、通义千问、智谱、硅基流动、OpenAI、Claude、Gemini、OpenRouter、Groq、Mistral 的预设及自定义服务。可直接读取账号/本机可用模型；模型列表不可用时支持手填。保存并测试后进入独立「AI 报告助手」进行报告关联、多轮追问、快捷问题和历史会话管理。

详见 [系统设置与接入指南](docs/SYSTEM_SETTINGS.md) 和 [报告助手说明](docs/REPORT_ASSISTANT.md)。

System settings owns upload limits, queue limits, report preferences and AI connections. The separate report assistant supports linked reports, multi-turn questions and persistent local conversations. Provider presets and model discovery share tested Ollama, Chat Completions and Anthropic Messages adapters. DeepSeek has been verified with the existing key; other live providers and local model installations require their own credentials/services.


## PDF 与科研图导出 / PDF and research figures

报告页提供「生成 PDF 报告」和「生成科研图包」。完成后显示下载按钮；已完成的历史任务也可使用，不重新运行清洗。可在提交任务前勾选自动生成 PDF。

PDF 使用 ReportLab 跨平台生成，常规安装不再需要 WeasyPrint/Pango。旧安装运行 `python start.py setup` 更新依赖；保留的 `requirements-pdf.txt` 仅供原版 HTML 转 PDF 引擎使用，不是本地版新入口的依赖。

科研图 ZIP 包含 3 种样式（academic_bw / standard_color / presentation），每种最多 7 类图：质量评分、PSD、波形、通道标准差、频段功率、头皮分布和步骤耗时。每图导出 300 dpi PNG、SVG、PDF；矢量容器中的栅格元素不会自动变成矢量。图内使用英文标注，包内附参数、指标、步骤和导出清单。

导出复用已保存的原始输入、清洗 FIF/EDF、参数、指标及步骤，需保留对应文件。不恢复未保存的 ICA 成分对象。缺少电极位置时，原绘图器可能使用标准模板或显示说明占位图；请检查导出提示及 manifest.json，发表前复核位置、单位和期刊要求。

PDF and research-figure exports are generated on demand from completed jobs, without rerunning cleaning. PDF uses the cross-platform ReportLab dependency. The figure ZIP includes three styles and up to seven figure types, in 300 dpi PNG, SVG and PDF, plus a manifest and processing metadata. Keep original inputs and cleaned FIF/EDF outputs. Historical ICA objects are not restored. Check placeholders, montage assumptions and partial-export warnings before publication.

Exports share the single cleaning executor and persist their state. Leaving the page does not cancel them. Interrupted exports can be retried after restart; failed exports preserve existing HTML and completed cleaning results.

## 开发和数据 / Development and data

```bash
python start.py backend
# another terminal
python start.py frontend
```

开发 UI 使用 5174；`python start.py build` 重建静态页面。`python start.py check` 检查后端导入。

任务、输入、结果和 AI 配置都在 `.local-data`。退出后可以备份该目录；没有自动删除数据功能，也不会恢复执行强制中断的任务。保持单个后端进程，不要使用多 worker 同时写入同一目录。

本版没有登录边界，仅供本机单用户使用，启动脚本固定绑定 127.0.0.1。不要改成 0.0.0.0 后公开部署。

## 版权与使用许可 / Copyright and license

个人可按 [完整许可](LICENSE.md) 免费用于非商业学习和研究、修改及按相同条款免费分享。商用和组织使用须另行获得书面授权。第三方数据、模型和代码保留各自许可，见 [第三方与权属说明](LICENSING.md)。

这是非商业源码许可，不是 OSI 定义的开源许可。软件、质量评分和 AI 解释可能出错，需独立复核，不构成医疗诊断。免责声明不排除法律禁止排除的责任。
