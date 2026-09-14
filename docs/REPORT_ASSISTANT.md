# 独立报告助手 / Standalone report assistant

AI 连接设置位于「系统设置」。报告助手单独用于问题、报告解读和本机对话历史。

1. 在系统设置选择本地模型或 API 服务，保存并测试连接。
2. 从报告页面进入 AI 助手，或在助手中选择一份已完成的报告。
3. 输入问题或点选快捷问题。只有明确勾选「本次附带关联报告的指标、参数和警告摘要」后，本次请求才附加摘要。选中报告本身不会发送摘要。
4. 发送后可继续追问；左侧可切换历史对话。每段对话固定关联一份报告，更换报告时新建对话。
5. 网络或模型请求失败时保留问题供重试，不把失败结果写入历史。

问题与当前对话的近期历史发送给系统设置中当前选定的模型服务。切换服务后，继续原对话也会发送历史，因此已生成的回答可能间接包含此前分享的报告内容。原始 EEG 文件不会发送。模型设置中控制携带历史轮数。使用新对话可避免沿用旧对话内容。

Configure and test your connection in System settings. Choose a completed report in the assistant, optionally check the report-summary consent box, then send a question. Continue with follow-up questions or open a locally saved conversation. Each conversation keeps its report association; start a new conversation for another report. Failed requests preserve the draft for retry.

Questions and recent conversation history are sent to the currently configured AI provider, including after changing providers. Historical answers may contain previously shared report information. Raw EEG recordings are never attached. Start a new conversation to avoid reusing previous conversation content.

## Implementation

- `frontend/src/components/ReportAssistant.tsx`: independent workspace, completed-job selector, starter prompts, conversation switching, request state and recoverable failures. Props: `en: boolean`, `initialJobId?: string`. It loads state when mounted or on entering `#/ai`, and listens for `brainifly-ai-settings-changed` to refresh after saving settings. No AI call or conversation creation occurs just by opening a report/page.
- `ReportAssistant.css`: white discussion surface, blue user-message marker, quiet cool-gray history column, existing system type stack. The asymmetric history/discussion layout follows the report workflow instead of repeating settings cards. Wider displays expand the discussion; narrow screens move history above it. Keyboard focus and form labels are explicit.
- Markdown rendering deliberately supports headings, bullets, bold, inline and fenced code as escaped React text. It never injects HTML or loads model-supplied images, links or scripts. Unsupported Markdown remains readable text.
- `backend/local_conversations.py`: `ConversationStore(root)` writes `.local-data/conversations/{id}.json`. Methods: `create(job_id=None, title=None)`, `list()`, `get(id)`, `append_exchange(id, question, answer, include_summary=False)` and `request_lock(id)`. JSON writes are atomic; read/write operations use an RLock and return deep copies. Per-conversation request locks let the API reject overlapping requests. Only successful question/answer pairs enter history.
- API: `GET/POST /api/conversations`, `GET /api/conversations/{id}`, `POST /api/conversations/{id}/messages` with `{question, include_summary}`. A conversation holds `id`, `title`, `job_id`, `messages`, `created_at`, `updated_at`. Messages contain `role`, `content`, `created_at` and optionally user `include_summary`.

原云端 AIChat 中的对话导航、快捷问题和报告关联已作为工作流参考；未迁入账号额度、支付或占位式检索动画，也未声称支持真实论文搜索。

Live browser/viewport verification depends on the available browser connection; compile and API checks do not substitute for visual acceptance.
