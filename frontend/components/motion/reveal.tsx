"use client";

import { ReactNode, useLayoutEffect, useRef } from "react";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";

gsap.registerPlugin(ScrollTrigger);

type RevealProps = {
  children: ReactNode;
  className?: string;
  delay?: number;
};

export function Reveal({ children, className = "", delay = 0 }: RevealProps) {
  const ref = useRef<HTMLDivElement>(null);

  useLayoutEffect(() => {
    if (!ref.current || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

    const context = gsap.context(() => {
      gsap.fromTo(
        ref.current,
        { autoAlpha: 0, y: 18 },
        {
          autoAlpha: 1,
          y: 0,
          duration: 0.68,
          delay,
          ease: "power3.out",
          clearProps: "transform",
          scrollTrigger: { trigger: ref.current, start: "top 88%", once: true },
        },
      );
    }, ref);

    return () => context.revert();
  }, [delay]);

  return <div ref={ref} className={className}>{children}</div>;
}

type TextRevealProps = RevealProps & {
  as?: "div" | "h1" | "h2" | "h3" | "p" | "span";
};

export function TextReveal({ children, className = "", delay = 0, as = "div" }: TextRevealProps) {
  const ref = useRef<HTMLElement | null>(null);

  useLayoutEffect(() => {
    if (!ref.current || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

    const context = gsap.context(() => {
      gsap.fromTo(
        ref.current,
        { autoAlpha: 0, y: 20, clipPath: "inset(0 0 100% 0)" },
        {
          autoAlpha: 1,
          y: 0,
          clipPath: "inset(0 0 0% 0)",
          duration: 0.82,
          delay,
          ease: "power3.out",
          clearProps: "transform,clipPath",
        },
      );
    }, ref);

    return () => context.revert();
  }, [delay]);

  return (
    <>
      {(() => {
        const Tag = as;
        return <Tag ref={(node) => { ref.current = node; }} className={className}>{children}</Tag>;
      })()}
    </>
  );
}
