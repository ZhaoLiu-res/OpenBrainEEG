/** Labelled synthetic illustration; never represents user data. */
export default function SignalIllustration({ en }: { en: boolean }) {
  const channels = ["Fp1", "Fp2", "C3", "C4", "Pz"];
  const wave = (channel: number) => Array.from({ length: 241 }, (_, i) => {
    const x = 62 + i * 2;
    const baseline = 56 + channel * 46;
    const oscillation = Math.sin(i * .38 + channel) * 5 + Math.sin(i * .91 + channel * .7) * 2.3 + Math.sin(i * .071) * 4;
    const event = Math.exp(-((i - 112 - channel * 4) ** 2) / 80) * Math.sin(i * .45) * 12;
    return `${i ? "L" : "M"}${x.toFixed(1)},${(baseline + oscillation + event).toFixed(1)}`;
  }).join(" ");
  return <figure className="hero-signal">
    <figcaption className="signal-caption"><strong>{en ? "A closer look at the signal" : "从每一段信号开始"}</strong><span>{en ? "Illustration · Synthetic traces" : "示意图 · 合成波形"}</span></figcaption>
    <svg viewBox="0 0 576 296" role="img" aria-label={en ? "Five synthetic EEG traces, for illustration only; not a processing result." : "五条合成脑电通道示意，仅用于展示，不代表处理结果。"}>
      {Array.from({ length: 13 }, (_, i) => <line key={`v${i}`} x1={62 + i * 40} y1="28" x2={62 + i * 40} y2="260" stroke="#edf1f7" />)}
      {channels.map((channel, i) => <g key={channel}>
        <line x1="62" y1={56 + i * 46} x2="542" y2={56 + i * 46} stroke="#e5ebf4" />
        <text x="18" y={60 + i * 46} fill="#596a80" fontSize="12" fontFamily="inherit">{channel}</text>
        <path d={wave(i)} fill="none" stroke={i === 2 ? "#245bd8" : "#7297d6"} strokeWidth={i === 2 ? "1.8" : "1.3"} strokeLinejoin="round" />
      </g>)}
      <text x="62" y="282" fill="#596a80" fontSize="11" fontFamily="inherit">{en ? "Time →" : "时间 →"}</text>
    </svg>
    <div className="signal-footnote">{en ? "Import a recording to inspect your own signals and quality report." : "导入录波后，即可查看真实信号与完整质量报告。"}</div>
  </figure>;
}
