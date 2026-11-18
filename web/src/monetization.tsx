/**
 * 유료화 전환 지점을 한곳에 모아 둔다. 지금은 전부 무료.
 *
 * - 해설 열람 제한(구독/건당 결제): canViewExplanation() 만 바꾸면 된다.
 * - 광고: VITE_AD_CLIENT 환경변수를 넣고 빌드하면 <AdSlot/> 자리에 광고가 들어간다.
 */
import { useEffect, useRef } from "react";
import type { ItemRef } from "./types";

// eslint-disable-next-line @typescript-eslint/no-unused-vars
export function canViewExplanation(_ref: ItemRef): boolean {
  return true;
}

const AD_CLIENT = import.meta.env.VITE_AD_CLIENT as string | undefined;

export function AdSlot({ slot }: { slot: string }) {
  const ref = useRef<HTMLModElement>(null);
  useEffect(() => {
    if (!AD_CLIENT || !ref.current) return;
    if (!document.querySelector("script[data-ad]")) {
      const s = document.createElement("script");
      s.async = true;
      s.dataset.ad = "1";
      s.src = `https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=${AD_CLIENT}`;
      s.crossOrigin = "anonymous";
      document.head.appendChild(s);
    }
    try {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      ((window as any).adsbygoogle ||= []).push({});
    } catch {
      /* noop */
    }
  }, []);
  if (!AD_CLIENT) return null;
  return <ins ref={ref} className="adsbygoogle ad-slot" data-ad-client={AD_CLIENT} data-ad-slot={slot} data-ad-format="auto" />;
}
