"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

type CalculatorProps = {
  onUnlock: () => void;
};

type Operator = "+" | "−" | "×" | "÷";

const UNLOCK_CODE_STORAGE_KEY = "aegis.unlock-code";
const DEFAULT_UNLOCK_CODE = "2580";

const operatorSymbols = new Set(["+", "−", "×", "÷"]);

function getUnlockCode() {
  if (typeof window === "undefined") return DEFAULT_UNLOCK_CODE;

  const savedCode = window.localStorage.getItem(UNLOCK_CODE_STORAGE_KEY);
  return savedCode && /^\d{4,6}$/.test(savedCode)
    ? savedCode
    : DEFAULT_UNLOCK_CODE;
}

function formatNumber(value: number) {
  if (!Number.isFinite(value)) throw new Error("That calculation is not valid.");

  const rounded = Number(value.toPrecision(12));
  return rounded.toString();
}

function evaluateExpression(expression: string) {
  const compactExpression = expression
    .replaceAll(" ", "")
    .replaceAll("−", "-")
    .replaceAll("×", "*")
    .replaceAll("÷", "/");

  if (!compactExpression) return 0;

  const rawTokens = compactExpression.match(/(?:\d*\.?\d+|[+\-*/])/g);
  if (!rawTokens || rawTokens.join("") !== compactExpression) {
    throw new Error("Please check the expression.");
  }

  const tokens: string[] = [];
  for (let index = 0; index < rawTokens.length; index += 1) {
    const token = rawTokens[index];
    const previous = rawTokens[index - 1];
    const isUnaryMinus =
      token === "-" &&
      (index === 0 || (previous && ["+", "-", "*", "/"].includes(previous)));

    if (isUnaryMinus) {
      const next = rawTokens[index + 1];
      if (!next || !/^\d*\.?\d+$/.test(next)) {
        throw new Error("Please check the expression.");
      }
      tokens.push(`-${next}`);
      index += 1;
    } else {
      tokens.push(token);
    }
  }

  const precedence: Record<string, number> = { "+": 1, "-": 1, "*": 2, "/": 2 };
  const output: string[] = [];
  const operators: string[] = [];

  for (const token of tokens) {
    if (!Number.isNaN(Number(token))) {
      output.push(token);
      continue;
    }

    while (
      operators.length > 0 &&
      precedence[operators[operators.length - 1]] >= precedence[token]
    ) {
      output.push(operators.pop() as string);
    }
    operators.push(token);
  }

  while (operators.length > 0) output.push(operators.pop() as string);

  const values: number[] = [];
  for (const token of output) {
    if (!Number.isNaN(Number(token))) {
      values.push(Number(token));
      continue;
    }

    const right = values.pop();
    const left = values.pop();
    if (left === undefined || right === undefined) {
      throw new Error("Please check the expression.");
    }

    if (token === "+") values.push(left + right);
    if (token === "-") values.push(left - right);
    if (token === "*") values.push(left * right);
    if (token === "/") {
      if (right === 0) throw new Error("Cannot divide by zero.");
      values.push(left / right);
    }
  }

  if (values.length !== 1) throw new Error("Please check the expression.");
  return values[0];
}

function replaceCurrentNumber(expression: string, value: string) {
  if (!expression || !/[\d.]$/.test(expression)) return value;
  return expression.replace(/-?\d*\.?\d+$/, value);
}

export default function Calculator({ onUnlock }: CalculatorProps) {
  const [expression, setExpression] = useState("");
  const [display, setDisplay] = useState("0");
  const [justEvaluated, setJustEvaluated] = useState(false);
  const [awaitingOperand, setAwaitingOperand] = useState(false);
  const [hasError, setHasError] = useState(false);

  const unlockCode = useMemo(() => getUnlockCode(), []);

  const clear = useCallback(() => {
    setExpression("");
    setDisplay("0");
    setJustEvaluated(false);
    setAwaitingOperand(false);
    setHasError(false);
  }, []);

  const appendDigit = useCallback(
    (digit: string) => {
      const startsNewOperand = justEvaluated || awaitingOperand;
      setHasError(false);
      setJustEvaluated(false);
      setAwaitingOperand(false);
      setExpression((currentExpression) => {
        if (justEvaluated || !currentExpression) return digit;
        return currentExpression + digit;
      });
      setDisplay((currentDisplay) => {
        if (startsNewOperand || currentDisplay === "0") return digit;
        return currentDisplay + digit;
      });
    },
    [awaitingOperand, justEvaluated],
  );

  const appendDecimal = useCallback(() => {
    const startsNewOperand = justEvaluated || awaitingOperand;
    setHasError(false);
    setJustEvaluated(false);
    setAwaitingOperand(false);
    setExpression((currentExpression) => {
      if (startsNewOperand || !currentExpression) return "0.";
      if (currentExpression.endsWith(" ")) return `${currentExpression}0.`;
      if (currentExpression.split(" ").at(-1)?.includes(".")) {
        return currentExpression;
      }
      return `${currentExpression}.`;
    });
    setDisplay((currentDisplay) => {
      if (startsNewOperand || currentDisplay === "0") return "0.";
      return currentDisplay.includes(".") ? currentDisplay : `${currentDisplay}.`;
    });
  }, [awaitingOperand, justEvaluated]);

  const chooseOperator = useCallback(
    (operator: Operator) => {
      if (hasError) return;
      setJustEvaluated(false);
      setAwaitingOperand(true);
      setExpression((currentExpression) => {
        const base = justEvaluated || !currentExpression ? display : currentExpression;
        if (operatorSymbols.has(base.trim().slice(-1))) {
          return `${base.trim().slice(0, -1)} ${operator} `;
        }
        return `${base.trim()} ${operator} `;
      });
    },
    [display, hasError, justEvaluated],
  );

  const toggleSign = useCallback(() => {
    if (hasError || display === "0") return;
    const nextValue = display.startsWith("-") ? display.slice(1) : `-${display}`;
    setDisplay(nextValue);
    setAwaitingOperand(false);
    setExpression((currentExpression) => replaceCurrentNumber(currentExpression, nextValue));
  }, [display, hasError]);

  const percent = useCallback(() => {
    if (hasError) return;
    const nextValue = formatNumber(Number(display) / 100);
    setDisplay(nextValue);
    setAwaitingOperand(false);
    setExpression((currentExpression) => replaceCurrentNumber(currentExpression, nextValue));
  }, [display, hasError]);

  const backspace = useCallback(() => {
    if (hasError) {
      clear();
      return;
    }

    setJustEvaluated(false);
    setAwaitingOperand(false);
    setExpression((currentExpression) => {
      const nextExpression = currentExpression.endsWith(" ")
        ? currentExpression.trimEnd().slice(0, -1).trimEnd()
        : currentExpression.slice(0, -1);
      return nextExpression;
    });
    setDisplay((currentDisplay) => {
      if (currentDisplay.length <= 1 || (currentDisplay.length === 2 && currentDisplay.startsWith("-"))) {
        return "0";
      }
      return currentDisplay.slice(0, -1);
    });
  }, [clear, hasError]);

  const calculate = useCallback(() => {
    const candidate = (expression || display).replaceAll(" ", "");

    if (/^\d{4,6}$/.test(candidate) && candidate === unlockCode) {
      clear();
      onUnlock();
      return;
    }

    try {
      const result = formatNumber(evaluateExpression(expression || display));
      setExpression(result);
      setDisplay(result);
      setJustEvaluated(true);
      setAwaitingOperand(false);
      setHasError(false);
    } catch (error) {
      setExpression("");
      setDisplay(error instanceof Error ? error.message : "Error");
      setHasError(true);
      setJustEvaluated(true);
    }
  }, [clear, display, expression, onUnlock, unlockCode]);

  useEffect(() => {
    const handleKeyboard = (event: KeyboardEvent) => {
      const key = event.key;

      if (/^\d$/.test(key)) {
        event.preventDefault();
        appendDigit(key);
      } else if (key === ".") {
        event.preventDefault();
        appendDecimal();
      } else if (["+", "-", "*", "/"].includes(key)) {
        event.preventDefault();
        chooseOperator(key === "-" ? "−" : key === "*" ? "×" : key === "/" ? "÷" : "+");
      } else if (key === "Enter" || key === "=") {
        event.preventDefault();
        calculate();
      } else if (key === "Backspace") {
        event.preventDefault();
        backspace();
      } else if (key === "%") {
        event.preventDefault();
        percent();
      } else if (key.toLowerCase() === "c" || key === "Escape") {
        event.preventDefault();
        clear();
      }
    };

    window.addEventListener("keydown", handleKeyboard);
    return () => window.removeEventListener("keydown", handleKeyboard);
  }, [appendDecimal, appendDigit, backspace, calculate, chooseOperator, clear, percent]);

  const keys = [
    { label: "AC", action: clear, style: "utility", ariaLabel: "Clear" },
    { label: "⌫", action: backspace, style: "utility", ariaLabel: "Backspace" },
    { label: "%", action: percent, style: "utility", ariaLabel: "Percent" },
    { label: "÷", action: () => chooseOperator("÷"), style: "operator", ariaLabel: "Divide" },
    { label: "7", action: () => appendDigit("7"), style: "number" },
    { label: "8", action: () => appendDigit("8"), style: "number" },
    { label: "9", action: () => appendDigit("9"), style: "number" },
    { label: "×", action: () => chooseOperator("×"), style: "operator", ariaLabel: "Multiply" },
    { label: "4", action: () => appendDigit("4"), style: "number" },
    { label: "5", action: () => appendDigit("5"), style: "number" },
    { label: "6", action: () => appendDigit("6"), style: "number" },
    { label: "−", action: () => chooseOperator("−"), style: "operator", ariaLabel: "Subtract" },
    { label: "1", action: () => appendDigit("1"), style: "number" },
    { label: "2", action: () => appendDigit("2"), style: "number" },
    { label: "3", action: () => appendDigit("3"), style: "number" },
    { label: "+", action: () => chooseOperator("+"), style: "operator", ariaLabel: "Add" },
    { label: "±", action: toggleSign, style: "number", ariaLabel: "Toggle sign" },
    { label: "0", action: () => appendDigit("0"), style: "number" },
    { label: ".", action: appendDecimal, style: "number", ariaLabel: "Decimal" },
    { label: "=", action: calculate, style: "equals", ariaLabel: "Equals" },
  ];

  return (
    <main className="calculator-stage">
      <section className="calculator" aria-label="Calculator">
        <div className="calculator-topbar">
          <span className="calculator-speaker" aria-hidden="true" />
          <span>Calculator</span>
          <span className="calculator-signal" aria-hidden="true">•••</span>
        </div>

        <div className="calculator-display" aria-live="polite">
          <span className="calculator-expression">{expression || "Ready"}</span>
          <span className={`calculator-value${hasError ? " is-error" : ""}`}>{display}</span>
        </div>

        <div className="calculator-grid">
          {keys.map((key) => (
            <button
              className={`calculator-key calculator-key-${key.style}`}
              key={key.label}
              type="button"
              onClick={key.action}
              aria-label={key.ariaLabel ?? key.label}
            >
              {key.label}
            </button>
          ))}
        </div>

        <p className="calculator-footer">Swipe up to see recent calculations</p>
      </section>
    </main>
  );
}
