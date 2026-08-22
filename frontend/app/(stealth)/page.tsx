"use client";

import { useCallback, useEffect, useState } from "react";
import Calculator from "./calculator";
import MainApp from "../(main)/main-app";

type AppMode = "calculator" | "aegis";

export default function StealthShell() {
  const [mode, setMode] = useState<AppMode>("calculator");

  const enterAegis = useCallback(() => {
    setMode("aegis");
  }, []);

  const panicExit = useCallback(() => {
    // Unmounting the real app clears its in-memory conversation and screen state.
    setMode("calculator");
  }, []);

  useEffect(() => {
    if (mode !== "aegis") return;

    const handlePanicKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        panicExit();
      }
    };

    window.addEventListener("keydown", handlePanicKey);
    return () => window.removeEventListener("keydown", handlePanicKey);
  }, [mode, panicExit]);

  if (mode === "aegis") {
    return <MainApp onPanicExit={panicExit} />;
  }

  return <Calculator onUnlock={enterAegis} />;
}
