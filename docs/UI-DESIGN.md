# Brainifly Local UI / 界面设计

## 方向与设计审查

面向脑电研究者的仪器工作台：白色工作面、冷灰背景、钴蓝操作色，保留数据导入、样例、任务、报告与 AI 流程。原版大块苔绿背景及反复覆盖的 CSS 容易显得灰暗，现改为一套统一样式。

初稿是白色卡片加流程列表。审查后移除了首页重复卡片外框，将唯一主视觉改为脑电通道示意，以贴合科研工具。示意明确标注为合成波形，不能与用户处理结果混淆。实际报告仍使用原始报告生成器。

色彩：Ink `#18283F`、Secondary `#596A80`、Action `#245BD8`、Canvas `#F5F7FB`、Surface `#FFFFFF`、Border `#DCE3ED`。绿色仅用于完成状态。状态同时有文字，不能仅凭颜色判断。

字体使用本机 Segoe UI Variable / Segoe UI / PingFang SC / Microsoft YaHei，不下载远程字体。正文 16px，辅助文字 13–15px，区块标题 22px；表格数字使用等宽数字特性。正文左对齐，首页段落限制行长，工作区本身不设置最大宽度。

```text
导航栏  | 页面位置                           语言设置
        | 介绍 + 开始操作         脑电通道示意
        | 处理流程介绍 / 报告说明 / 可选 AI
        | 最近任务表格：查看报告

导航栏  | 报告信息、下载与质量指标
        | 完整报告 iframe（占满可用工作区）
        | 参数与处理日志
```

## 响应式与可访问性

- 1980px 视口：264px 导航栏，可用主区域 1716px；左右各约59px内边距。
- 2560px 视口：288px 导航栏，可用主区域 2272px；左右各64px内边距。
- 1280px 以下内容转为单列；760px 以下导航回到文档流。
- 键盘焦点使用蓝色轮廓；文件导入区域通过 focus-within 显示焦点，保留系统缩放。
- 报告、长文件名、模型回复可换行或在容器内滚动；不通过隐藏整页溢出来掩盖排版问题。
- 不采用自动播放动效，仍提供减少动态效果的系统偏好支持。

## 验证边界

本次按 [Web Interface Guidelines](https://raw.githubusercontent.com/vercel-labs/web-interface-guidelines/main/command.md) 审查样式及交互语义建议。样式源码已核查焦点、长内容、宽屏计算、移动断点；主界面交互修改和构建结果由集成验证记录负责。

当前无可用浏览器控制连接，尚未执行1980×1280或2560×1440实机截图验收，不能将 CSS 断点检查等同于视觉验收。内嵌报告为独立文档，其样式不受工作台 CSS 影响。

English: An EEG research workspace with white surfaces, a cool gray canvas and a single blue action color. The labelled synthetic trace is an illustration, not a computed result. The fluid layout supports large desktop targets and switches to stacked navigation on narrow screens. Keyboard focus and reduced-motion preferences are respected. Browser screenshot verification remains pending.
