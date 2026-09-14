# 系统设置与 AI 接入 / System settings & AI connections

## 使用入口

- 系统设置：`http://127.0.0.1:8765/#/settings`。
- 独立报告助手：`http://127.0.0.1:8765/#/ai`。
- 历史报告中点击「向 AI 提问」，可在助手中关联对应报告；需要发送报告指标时勾选摘要选项。

## DeepSeek 修复

此次实际保存状态为「provider=disabled，已保存密钥」，不是密钥必然失效。修复了启用时保留同地址密钥的逻辑，提供「保存并测试连接」一步完成启用、保存与测试。已用现有密钥实际读取 DeepSeek 模型列表并完成短问答和两轮上下文验证，配置已启用；没有把密钥写入文档、浏览器存储或日志。

操作：选择 API Key → DeepSeek → 填写密钥（已保存可留空）→ 读取可用模型或保留预设 → 保存并测试连接 → 打开报告助手。读取模型列表使用当前表单，不必先填写模型名。选择模型不会自动发送问题。

## 可配置的系统项

| 配置 | 默认 | 范围 / 作用 |
| --- | --- | --- |
| 单文件大小 | 512 MB | 1–8192 MB，前端与后端检查，新上传生效 |
| 活动任务总数 | 4 | 1–16，包含运行和排队；仍只执行一个清洗任务 |
| 报告语言 | 跟随界面 | 中文 / English / 跟随界面，新任务生效 |
| 默认 PDF | 关闭 | 可在每次清洗时调整，PDF 仍需系统依赖 |
| 完成自动打开报告 | 开启 | 关闭后保留任务结果入口，手动点击查看报告 |
| AI 超时 | 120 秒（旧配置保留原值） | 5–600 秒 |
| AI 历史轮数 | 10 | 0–40，历史另有 60000 字符预算 |
| AI 输出上限 | 2048 tokens | 128–16384；推理模型过低可能没有正文 |

设置保存到 `.local-data/system-settings.json`；AI 配置到 `.local-data/ai-settings.json`；会话到 `.local-data/conversations`。目前保存一套生效的 AI 连接。切换地址不会沿用上一家服务的密钥。关闭 AI 后同一地址的密钥仍可保留，勾选清除可删除。

## 服务预设

下表为常见服务入口，不等于市场上全部模型，也不保证账号拥有每个模型权限。尽量从「读取可用模型」中选择文本对话模型，或按账户文档手动填写；部分服务的模型列表不开放，手填后仍可测试。国内/国际地区、Coding Plan 专属端点或推理接入点 ID 需按购买的产品调整，不能把不同产品的 Key 混用。

| 服务 | Base URL | 协议 | 官方说明 |
| --- | --- | --- | --- |
| Ollama | `http://localhost:11434` | ollama | [文档](https://docs.ollama.com/api/tags) |
| LM Studio | `http://localhost:1234/v1` | openai_compatible | [文档](https://lmstudio.ai/docs/developer/openai-compat) |
| vLLM / llama.cpp | `http://localhost:8000/v1` | openai_compatible | [文档](https://docs.vllm.ai/en/latest/serving/online_serving/openai_compatible_server/) |
| DeepSeek | `https://api.deepseek.com` | openai_compatible | [文档](https://api-docs.deepseek.com/) |
| Kimi / Moonshot | `https://api.moonshot.cn/v1` | openai_compatible | [文档](https://platform.kimi.com/docs/get-api-key) |
| 豆包 / 火山方舟 | `https://ark.cn-beijing.volces.com/api/v3` | openai_compatible | [文档](https://www.volcengine.com/docs/82379/1795150) |
| 通义千问 / Qwen | `https://dashscope.aliyuncs.com/compatible-mode/v1` | openai_compatible | [文档](https://help.aliyun.com/zh/model-studio/compatibility-of-openai-with-dashscope) |
| 智谱 / GLM | `https://open.bigmodel.cn/api/paas/v4` | openai_compatible | [文档](https://docs.bigmodel.cn/cn/guide/develop/openai/introduction) |
| 硅基流动 / SiliconFlow | `https://api.siliconflow.cn/v1` | openai_compatible | [文档](https://docs.siliconflow.cn/docs/api/chat-completions-post) |
| OpenAI | `https://api.openai.com/v1` | openai_compatible | [文档](https://developers.openai.com/api/reference/resources/chat) |
| Claude / Anthropic | `https://api.anthropic.com/v1` | anthropic | [文档](https://platform.claude.com/docs/en/api/overview) |
| Google Gemini | `https://generativelanguage.googleapis.com/v1beta/openai` | openai_compatible | [文档](https://ai.google.dev/gemini-api/docs/openai) |
| OpenRouter | `https://openrouter.ai/api/v1` | openai_compatible | [文档](https://openrouter.ai/docs/api_reference/overview) |
| Groq | `https://api.groq.com/openai/v1` | openai_compatible | [文档](https://console.groq.com/docs/openai) |
| Mistral | `https://api.mistral.ai/v1` | openai_compatible | [文档](https://docs.mistral.ai/api) |

另有自定义服务入口，可选三种协议。Claude 使用 Anthropic Messages 原生协议；其余云预设使用 Chat Completions 兼容格式。OpenAI 输出上限使用 max_completion_tokens，Ollama 使用 options.num_predict；不会给所有服务强加相同的温度或推理参数。

## Windows / macOS 本地模型

1. 在本机安装并启动 Ollama，准备一个适合本机资源的文本模型；或启动 LM Studio 的本地服务器并加载模型。
2. 系统设置选择「本地模型」，选择 Ollama 或 LM Studio。填入实际服务地址；默认分别为 `http://localhost:11434`、`http://localhost:1234/v1`。
3. 点击「读取可用模型」，选择已安装/可服务的模型。Ollama 请求 `/api/tags`，兼容服务请求 `/models`。
4. 点击「保存并测试连接」。实际推理分别使用 `/api/chat` 或 `/chat/completions`。
5. vLLM/llama.cpp 需先启动兼容服务器，填写它实际监听的端口。8000 若被其他 Brainifly 服务占用，应改用独立端口。

Windows 和 macOS 的 Brainifly 接入步骤相同，模型运行环境由相应软件提供。本轮没有自动安装或下载大模型；当前本机 Ollama/LM Studio 未运行，三种协议的本地 HTTP 调用已用测试服务验证，真实本地模型推理仍待用户启动模型后验证。

## 错误与验证范围

HTTP 401：检查 API Key；402：余额；403：权限/地区；404：Base URL/模型；429：限流/配额；超时：服务或超时设置。服务返回的任意原始错误正文不会直接显示，避免其中夹带凭据。

已实测 DeepSeek 模型列表、连接和多轮问答；其他服务为协议实现及本地 HTTP 测试通过，尚无各家真实账号逐项验收。浏览器控制连接不可用，尚未完成实际点击和截图验收。基础 EEG 清洗、历史报告与可选 AI 保持独立。

English: System settings now owns AI connections and upload/queue/report preferences. The report assistant is a separate multi-turn workspace with locally persisted conversations. Save & test activates the chosen connection explicitly. DeepSeek was verified using the existing key; other presets have protocol-level tests, not account-level certification. Local inference requires a running model server. Raw EEG is never automatically sent; questions and conversation history go to the selected service, and report metrics are included only when explicitly selected.
