"""Endpoint presets, verified against linked provider documentation (2026-09-14).
Model IDs are discovered from each account/server, not an exhaustive static list.
"""
def item(id, name, url, doc, mode="api", protocol="openai_compatible", model=""):
    return dict(id=id, name=name, base_url=url, documentation=doc, mode=mode, provider=protocol, model=model)


PROVIDERS = [
    item("ollama", "Ollama", "http://localhost:11434", "https://docs.ollama.com/api/tags", "local", "ollama"),
    item("lmstudio", "LM Studio", "http://localhost:1234/v1", "https://lmstudio.ai/docs/developer/openai-compat", "local"),
    item("vllm", "vLLM / llama.cpp", "http://localhost:8000/v1", "https://docs.vllm.ai/en/latest/serving/online_serving/openai_compatible_server/", "local"),
    item("deepseek", "DeepSeek", "https://api.deepseek.com", "https://api-docs.deepseek.com/", model="deepseek-flash"),
    item("kimi", "Kimi / Moonshot", "https://api.moonshot.cn/v1", "https://platform.kimi.com/docs/get-api-key", model="kimi-k3"),
    item("doubao", "豆包 / 火山方舟", "https://ark.cn-beijing.volces.com/api/v3", "https://www.volcengine.com/docs/82379/1795150"),
    item("qwen", "通义千问 / Qwen", "https://dashscope.aliyuncs.com/compatible-mode/v1", "https://help.aliyun.com/zh/model-studio/compatibility-of-openai-with-dashscope"),
    item("zhipu", "智谱 / GLM", "https://open.bigmodel.cn/api/paas/v4", "https://docs.bigmodel.cn/cn/guide/develop/openai/introduction"),
    item("siliconflow", "硅基流动 / SiliconFlow", "https://api.siliconflow.cn/v1", "https://docs.siliconflow.cn/docs/api/chat-completions-post"),
    item("openai", "OpenAI", "https://api.openai.com/v1", "https://developers.openai.com/api/reference/resources/chat"),
    item("claude", "Claude / Anthropic", "https://api.anthropic.com/v1", "https://platform.claude.com/docs/en/api/overview", protocol="anthropic"),
    item("gemini", "Google Gemini", "https://generativelanguage.googleapis.com/v1beta/openai", "https://ai.google.dev/gemini-api/docs/openai"),
    item("openrouter", "OpenRouter", "https://openrouter.ai/api/v1", "https://openrouter.ai/docs/api_reference/overview"),
    item("groq", "Groq", "https://api.groq.com/openai/v1", "https://console.groq.com/docs/openai"),
    item("mistral", "Mistral", "https://api.mistral.ai/v1", "https://docs.mistral.ai/api"),
]
