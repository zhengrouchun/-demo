import { useLayoutEffect, useRef, useState } from "react";
import type { PetContext, PetSettings, Position } from "./petState";
import { PET_CONFIG } from "./petConfig";

interface Props { settings: PetSettings; position: Position; petWidth: number; petHeight: number; viewWidth: number; viewHeight: number; onChange: (patch: Partial<PetSettings>) => void; onClose: () => void; onHide: () => void; onReset: () => void; onEncourage: (context: PetContext) => void; onWave: () => void }
export function PetMenu({ settings, position, petWidth, petHeight, viewWidth, viewHeight, onChange, onClose, onHide, onReset, onEncourage, onWave }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const [height, setHeight] = useState(360);
  useLayoutEffect(() => {
    const node = ref.current;
    if (!node) return;
    const observer = new ResizeObserver(() => setHeight(node.offsetHeight));
    observer.observe(node); setHeight(node.offsetHeight);
    return () => observer.disconnect();
  }, []);
  const width = Math.min(280, viewWidth - 16);
  const left = Math.max(8, Math.min(position.x + petWidth - width, viewWidth - width - 8));
  const top = Math.max(8, Math.min(position.y - height - 10 >= 8 ? position.y - height - 10 : position.y + petHeight + 10, viewHeight - height - 8));
  return <div ref={ref} className="gsp-menu" style={{ left, top, width, maxHeight: viewHeight - 16 }} role="dialog" aria-label="顾时夜桌宠设置"><div className="gsp-menu-heading"><div><small>陪伴设置</small><strong>顾时夜</strong></div><button className="gsp-icon" aria-label="关闭桌宠设置" onClick={onClose}>×</button></div><p className="gsp-menu-hint">点一下回应你，拖动换个位置。</p><div className="gsp-menu-greetings"><button onClick={onWave}>打个招呼</button><button onClick={() => onEncourage("coding")}>给我鼓励</button><button onClick={() => onEncourage("anxiety")}>陪我一会儿</button><button onClick={() => onEncourage("project")}>重要的一天</button></div><label className="gsp-scale">小人大小 <span>{Math.round(settings.scale * 100)}%</span><input aria-label="桌宠大小" type="range" min={PET_CONFIG.scale.min} max={PET_CONFIG.scale.max} step={PET_CONFIG.scale.step} value={settings.scale} onChange={e => onChange({ scale: Number(e.target.value) })} /></label>{([['randomActions', '偶尔眨眼、招手'], ['dialogueBubble', '显示对白气泡'], ['autoSleep', '久未操作时睡觉']] as const).map(([key, text]) => <label className="gsp-toggle" key={key}><span>{text}</span><input type="checkbox" checked={settings[key]} onChange={e => onChange({ [key]: e.target.checked })} /></label>)}<p className="gsp-version">V0.1 · 安静陪伴，不自动走动</p><div className="gsp-menu-footer"><button onClick={onReset}>回到右下角</button><button onClick={onHide}>暂时隐藏</button></div><span className="gsp-menu-tip">长时间无操作 {PET_CONFIG.sleep.timeout / 60000} 分钟后休息。</span></div>;
}
