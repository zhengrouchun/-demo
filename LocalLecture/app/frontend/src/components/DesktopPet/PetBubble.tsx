import { useLayoutEffect, useRef, useState } from "react";
import type { CSSProperties } from "react";
import { PET_CONFIG } from "./petConfig";
import type { Bubble, Position } from "./petState";

export function PetBubble({ bubble, position, petWidth, petHeight, viewWidth, viewHeight }: { bubble: Bubble; position: Position; petWidth: number; petHeight: number; viewWidth: number; viewHeight: number }) {
  const ref = useRef<HTMLDivElement>(null);
  const [height, setHeight] = useState(86);
  useLayoutEffect(() => {
    const node = ref.current;
    if (!node) return;
    const observer = new ResizeObserver(() => setHeight(node.offsetHeight));
    observer.observe(node); setHeight(node.offsetHeight);
    return () => observer.disconnect();
  }, []);
  const { maxWidth, edge, gap, fadeDuration } = PET_CONFIG.bubble;
  const width = Math.min(maxWidth, viewWidth - edge * 2);
  const center = position.x + petWidth / 2;
  const left = Math.max(edge, Math.min(center - width / 2, viewWidth - width - edge));
  const above = position.y - height - gap >= edge;
  const top = Math.max(edge, Math.min(above ? position.y - height - gap : position.y + petHeight + gap, viewHeight - height - edge));
  const style = { left, top, width, "--pet-arrow": `${Math.max(16, Math.min(center - left, width - 16))}px`, "--pet-fade": `${fadeDuration}ms` } as CSSProperties;
  return <div ref={ref} className="gsp-bubble" style={style} data-phase={bubble.phase} data-placement={above ? "above" : "below"} role="status" aria-live="polite"><span className="gsp-bubble-name">顾时夜</span><p>{bubble.text}</p></div>;
}
