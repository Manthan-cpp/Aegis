"use client";

import { ReactNode, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { ReactLenis, useLenis } from "lenis/react";

gsap.registerPlugin(ScrollTrigger);

type MotionProviderProps = {
  children: ReactNode;
};

function usePrefersReducedMotion() {
  const [reduced, setReduced] = useState(false);

  useEffect(() => {
    const media = window.matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => setReduced(media.matches);
    update();
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);

  return reduced;
}

function MotionCanvas({ children, reduced }: MotionProviderProps & { reduced: boolean }) {
  const lenis = useLenis();
  const rootRef = useRef<HTMLDivElement>(null);

  useLayoutEffect(() => {
    if (!lenis || reduced) return;

    const update = (time: number) => lenis.raf(time * 1000);
    const refresh = () => ScrollTrigger.update();

    lenis.on("scroll", refresh);
    gsap.ticker.add(update);
    gsap.ticker.lagSmoothing(0);

    return () => {
      lenis.off("scroll", refresh);
      gsap.ticker.remove(update);
    };
  }, [lenis, reduced]);

  useLayoutEffect(() => {
    if (!rootRef.current || reduced) return;

    const context = gsap.context(() => {
      const route = rootRef.current?.querySelector<HTMLElement>("[data-motion-route]");
      if (route) {
        gsap.fromTo(
          route,
          { autoAlpha: 0, y: 14 },
          { autoAlpha: 1, y: 0, duration: 0.58, ease: "power3.out", clearProps: "transform" },
        );
      }

      const intros = rootRef.current?.querySelectorAll<HTMLElement>("[data-motion-intro]") ?? [];
      intros.forEach((intro) => {
        gsap.fromTo(
          intro,
          { autoAlpha: 0, y: 12 },
          { autoAlpha: 1, y: 0, duration: 0.62, delay: 0.08, ease: "power3.out", clearProps: "transform" },
        );
      });

      const groups = rootRef.current?.querySelectorAll<HTMLElement>("[data-motion-stagger]") ?? [];
      groups.forEach((group) => {
        const items = group.querySelectorAll<HTMLElement>(":scope > [data-motion-item]");
        if (!items.length) return;
        gsap.fromTo(
          items,
          { autoAlpha: 0, y: 18 },
          {
            autoAlpha: 1,
            y: 0,
            duration: 0.65,
            delay: 0.12,
            stagger: 0.09,
            ease: "power3.out",
            clearProps: "transform",
            scrollTrigger: { trigger: group, start: "top 86%", once: true },
          },
        );
      });
    }, rootRef);

    return () => context.revert();
  }, [reduced]);

  return <div ref={rootRef} className="aegis-motion-canvas">{children}</div>;
}

export default function MotionProvider({ children }: MotionProviderProps) {
  const reduced = usePrefersReducedMotion();
  const options = useMemo(
    () => ({
      autoRaf: false,
      lerp: reduced ? 1 : 0.085,
      smoothWheel: !reduced,
      syncTouch: false,
      anchors: true,
      allowNestedScroll: false,
      respectReducedMotion: true,
    }),
    [reduced],
  );

  return (
    <ReactLenis root options={options}>
      <MotionCanvas reduced={reduced}>{children}</MotionCanvas>
    </ReactLenis>
  );
}
