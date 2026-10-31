import { useEffect, useState } from "react";
import { PET_ASSETS } from "./petConfig";
import type { PetState } from "./petState";

const requests = new Map<string, Promise<string | null>>();
function load(path: string) {
  if (!requests.has(path)) requests.set(path, new Promise(resolve => {
    const image = new Image();
    image.onload = () => resolve(path);
    image.onerror = () => resolve(null);
    image.src = path;
  }));
  return requests.get(path)!;
}
export function usePetAsset(state: PetState) {
  const [source, setSource] = useState<string | null>(null);
  useEffect(() => { for (const state of ["idle", "blink", "touch", "wave"] as const) void load(PET_ASSETS[state]); }, []);
  useEffect(() => {
    let alive = true;
    void (async () => { const preferred = await load(PET_ASSETS[state]); const fallback = preferred ?? await load(PET_ASSETS.idle); if (alive) setSource(fallback); })();
    return () => { alive = false; };
  }, [state]);
  return source;
}
