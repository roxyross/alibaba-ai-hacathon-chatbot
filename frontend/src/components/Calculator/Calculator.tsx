import React, { useState, useEffect, useRef } from 'react';
import { VoiceInputControl } from '../common/VoiceInputControl';
import './Calculator.css';

function parseSpokenMath(spoken: string): string {
  let s = spoken.toLowerCase()
    .replace(/what is|calculate|solve/g, '')
    .replace(/plus/g, '+')
    .replace(/minus/g, '-')
    .replace(/times|multiplied by/g, '*')
    .replace(/divided by|over/g, '/')
    .replace(/to the power of/g, '^')
    .replace(/square root of/g, '√')
    .replace(/percent of/g, '% *')
    .replace(/percentage of/g, '% *')
    .replace(/x/g, '*')
    .replace(/[=?]/g, '')
    .trim();
  return s;
}


interface CalculatorProps {
  onBack: () => void;
  onSendToChat?: (text: string) => void;
  accessToken?: string | null;
}

interface HistoryItem {
  id: string;
  expression: string;
  result: string;
  timestamp: string;
  source: 'client' | 'backend';
}

const API_BASE =
  (import.meta as { env: { VITE_API_BASE?: string } }).env.VITE_API_BASE ??
  '/api/v1';

export const Calculator: React.FC<CalculatorProps> = ({
  onBack,
  onSendToChat,
  accessToken,
}) => {
  const [expression, setExpression] = useState('');
  const [result, setResult] = useState<string>('');
  const [history, setHistory] = useState<HistoryItem[]>(() => {
    try {
      const saved = localStorage.getItem('roxy_calc_history');
      return saved ? JSON.parse(saved) : [];
    } catch {
      return [];
    }
  });
  const [isLoadingBackend, setIsLoadingBackend] = useState(false);
  const [lastSource, setLastSource] = useState<'client' | 'backend' | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    try {
      localStorage.setItem('roxy_calc_history', JSON.stringify(history.slice(0, 30)));
    } catch {
      // Ignore storage errors
    }
  }, [history]);

  // Client-side safe evaluator
  const calculateClient = (exprToEval: string): number => {
    // Replace visual symbols
    let sanitized = exprToEval
      .replace(/×/g, '*')
      .replace(/÷/g, '/')
      .replace(/π/g, `${Math.PI}`)
      .replace(/e/g, `${Math.E}`);

    // Handle percentage (e.g. 50% -> 0.5)
    sanitized = sanitized.replace(/([0-9.]+)%/g, '($1/100)');

    // Only allow safe math characters
    if (!/^[0-9+\-*/().\s^]+$/.test(sanitized)) {
      throw new Error('Invalid characters in expression');
    }

    // Handle power ^
    sanitized = sanitized.replace(/\^/g, '**');

    // Safe Function constructor with no scope access
    const fn = new Function(`"use strict"; return (${sanitized});`);
    const val = fn();
    if (typeof val !== 'number' || !isFinite(val)) {
      throw new Error('Invalid calculation result');
    }
    return val;
  };

  const handleEqual = async () => {
    if (!expression.trim()) return;
    setErrorMessage(null);

    try {
      const computed = calculateClient(expression);
      const resStr = Number.isInteger(computed)
        ? computed.toString()
        : computed.toFixed(6).replace(/\.?0+$/, '');

      setResult(resStr);
      setLastSource('client');

      const newItem: HistoryItem = {
        id: Date.now().toString(),
        expression,
        result: resStr,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        source: 'client',
      };
      setHistory((prev) => [newItem, ...prev.filter((h) => h.expression !== expression)]);
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : 'Syntax error');
    }
  };

  // Evaluate directly using backend Python AST skill
  const handleBackendEvaluate = async () => {
    if (!expression.trim()) return;
    setIsLoadingBackend(true);
    setErrorMessage(null);

    try {
      // Normalize operators for Python AST
      const pythonExpr = expression
        .replace(/×/g, '*')
        .replace(/÷/g, '/')
        .replace(/π/g, '3.1415926535')
        .replace(/\^/g, '**');

      const res = await fetch(`${API_BASE}/skills/calculator`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
        },
        body: JSON.stringify({ expression: pythonExpr }),
      });

      if (!res.ok) {
        throw new Error(`Backend returned HTTP ${res.status}`);
      }

      const data = await res.json();
      if (data.error) {
        throw new Error(data.error);
      }

      const resVal = data.result !== null ? String(data.result) : '0';
      setResult(resVal);
      setLastSource('backend');

      const newItem: HistoryItem = {
        id: Date.now().toString(),
        expression,
        result: resVal,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        source: 'backend',
      };
      setHistory((prev) => [newItem, ...prev.filter((h) => h.expression !== expression)]);
    } catch (err) {
      setErrorMessage(`Backend evaluation failed: ${err instanceof Error ? err.message : 'Unknown error'}`);
    } finally {
      setIsLoadingBackend(false);
    }
  };

  const handleKeyClick = (val: string) => {
    setErrorMessage(null);
    if (val === 'C') {
      setExpression('');
      setResult('');
    } else if (val === '⌫') {
      setExpression((prev) => prev.slice(0, -1));
    } else if (val === '=') {
      handleEqual();
    } else if (val === '±') {
      setExpression((prev) => {
        if (!prev) return '-';
        if (prev.startsWith('-')) return prev.slice(1);
        return '-' + prev;
      });
    } else if (val === '√') {
      try {
        const curr = result || expression;
        if (!curr) return;
        const num = calculateClient(curr);
        if (num < 0) throw new Error('Square root of negative number');
        const sq = Math.sqrt(num);
        const resStr = Number.isInteger(sq) ? sq.toString() : sq.toFixed(6).replace(/\.?0+$/, '');
        setExpression(`√(${curr})`);
        setResult(resStr);
      } catch (err) {
        setErrorMessage(err instanceof Error ? err.message : 'Error in sqrt');
      }
    } else if (val === 'x²') {
      try {
        const curr = result || expression;
        if (!curr) return;
        const num = calculateClient(curr);
        const sq = Math.pow(num, 2);
        const resStr = Number.isInteger(sq) ? sq.toString() : sq.toFixed(6).replace(/\.?0+$/, '');
        setExpression(`(${curr})²`);
        setResult(resStr);
      } catch (err) {
        setErrorMessage(err instanceof Error ? err.message : 'Error squaring');
      }
    } else if (val === '1/x') {
      try {
        const curr = result || expression;
        if (!curr) return;
        const num = calculateClient(curr);
        if (num === 0) throw new Error('Division by zero');
        const inv = 1 / num;
        const resStr = Number.isInteger(inv) ? inv.toString() : inv.toFixed(6).replace(/\.?0+$/, '');
        setExpression(`1/(${curr})`);
        setResult(resStr);
      } catch (err) {
        setErrorMessage(err instanceof Error ? err.message : 'Error in reciprocal');
      }
    } else {
      setExpression((prev) => prev + val);
    }
  };

  const handleSendResultToChat = () => {
    if (!onSendToChat) return;
    const textToSend = result
      ? `Calculate: ${expression} = ${result}`
      : `Calculate math expression: ${expression}`;
    onSendToChat(textToSend);
    onBack();
  };

  return (
    <div className="calculator-view">
      {/* Top Header */}
      <header className="calculator-header">
        <div className="calculator-header__left">
          <button type="button" className="view-back-btn" onClick={onBack} aria-label="Back to chat">
            ← Back to Chat
          </button>
          <div className="calculator-header__info">
            <h2 className="calculator-title">
              <span>🧮</span> ROXY Calculator
            </h2>
            <span className="calculator-badge">Backend Python Skill Active</span>
          </div>
        </div>

        <div className="calculator-header__actions">
          <VoiceInputControl
            size="sm"
            showLangPicker={true}
            showReadAloud={Boolean(result)}
            readAloudText={result ? `${expression} equals ${result}` : ''}
            onTranscript={(text) => {
              const parsed = parseSpokenMath(text);
              setExpression(parsed);
              setTimeout(() => {
                try {
                  const val = calculateClient(parsed);
                  const resStr = Number.isInteger(val)
                    ? val.toString()
                    : val.toFixed(6).replace(/\.?0+$/, '');
                  setResult(resStr);
                  setLastSource('client');
                } catch {
                  // user can hit equal button
                }
              }, 150);
            }}
            label="Speak math expression"
          />
          {history.length > 0 && (
            <button
              type="button"
              className="calculator-btn-clear-history"
              onClick={() => setHistory([])}
              title="Clear calculation history"
            >
              Clear History
            </button>
          )}
        </div>
      </header>

      {/* Main Content Layout */}
      <div className="calculator-layout">
        {/* Left: Calculator Card */}
        <div className="calculator-card">
          {/* Display */}
          <div className="calculator-display">
            <div className="calculator-display__expression" style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <input
                ref={inputRef}
                type="text"
                value={expression}
                placeholder="0 (or click mic to speak calculation)"
                onChange={(e) => setExpression(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    e.preventDefault();
                    handleEqual();
                  }
                }}
                className="calculator-input"
              />
              <VoiceInputControl
                size="sm"
                showReadAloud={false}
                onTranscript={(text) => {
                  const parsed = parseSpokenMath(text);
                  setExpression(parsed);
                }}
                label="Voice math input"
              />
            </div>

            <div className="calculator-display__result">
              {result ? (
                <>
                  <span className="calculator-equals">=</span>
                  <span className="calculator-val">{result}</span>
                  {lastSource && (
                    <span className="calculator-source-tag">
                      {lastSource === 'backend' ? 'Python AST' : 'Fast Eval'}
                    </span>
                  )}
                </>
              ) : (
                <span className="calculator-placeholder">Press = to compute</span>
              )}
            </div>
          </div>

          {errorMessage && (
            <div className="calculator-error" role="alert">
              ⚠️ {errorMessage}
            </div>
          )}

          {/* Action Row */}
          <div className="calculator-quick-actions">
            <button
              type="button"
              className="calculator-action-btn calculator-action-btn--backend"
              onClick={handleBackendEvaluate}
              disabled={isLoadingBackend || !expression.trim()}
              title="Evaluate using backend Python AST parser"
            >
              {isLoadingBackend ? 'Computing…' : '⚡ Python Backend Skill'}
            </button>

            {result && onSendToChat && (
              <button
                type="button"
                className="calculator-action-btn calculator-action-btn--chat"
                onClick={handleSendResultToChat}
                title="Send calculation into chat session"
              >
                💬 Send to Chat
              </button>
            )}
          </div>

          {/* Keypad Grid */}
          <div className="calculator-grid">
            {/* Row 1 */}
            <button type="button" className="calc-key calc-key--fn" onClick={() => handleKeyClick('C')}>C</button>
            <button type="button" className="calc-key calc-key--fn" onClick={() => handleKeyClick('⌫')}>⌫</button>
            <button type="button" className="calc-key calc-key--op" onClick={() => handleKeyClick('(')}>(</button>
            <button type="button" className="calc-key calc-key--op" onClick={() => handleKeyClick(')')}>)</button>
            <button type="button" className="calc-key calc-key--op" onClick={() => handleKeyClick('%')}>%</button>
            <button type="button" className="calc-key calc-key--op" onClick={() => handleKeyClick('÷')}>÷</button>

            {/* Row 2 */}
            <button type="button" className="calc-key calc-key--num" onClick={() => handleKeyClick('7')}>7</button>
            <button type="button" className="calc-key calc-key--num" onClick={() => handleKeyClick('8')}>8</button>
            <button type="button" className="calc-key calc-key--num" onClick={() => handleKeyClick('9')}>9</button>
            <button type="button" className="calc-key calc-key--op" onClick={() => handleKeyClick('×')}>×</button>
            <button type="button" className="calc-key calc-key--fn" onClick={() => handleKeyClick('x²')}>x²</button>
            <button type="button" className="calc-key calc-key--fn" onClick={() => handleKeyClick('√')}>√</button>

            {/* Row 3 */}
            <button type="button" className="calc-key calc-key--num" onClick={() => handleKeyClick('4')}>4</button>
            <button type="button" className="calc-key calc-key--num" onClick={() => handleKeyClick('5')}>5</button>
            <button type="button" className="calc-key calc-key--num" onClick={() => handleKeyClick('6')}>6</button>
            <button type="button" className="calc-key calc-key--op" onClick={() => handleKeyClick('-')}>-</button>
            <button type="button" className="calc-key calc-key--fn" onClick={() => handleKeyClick('^')}>^</button>
            <button type="button" className="calc-key calc-key--fn" onClick={() => handleKeyClick('1/x')}>1/x</button>

            {/* Row 4 */}
            <button type="button" className="calc-key calc-key--num" onClick={() => handleKeyClick('1')}>1</button>
            <button type="button" className="calc-key calc-key--num" onClick={() => handleKeyClick('2')}>2</button>
            <button type="button" className="calc-key calc-key--num" onClick={() => handleKeyClick('3')}>3</button>
            <button type="button" className="calc-key calc-key--op" onClick={() => handleKeyClick('+')}>+</button>
            <button type="button" className="calc-key calc-key--fn" onClick={() => handleKeyClick('±')}>±</button>
            <button type="button" className="calc-key calc-key--fn" onClick={() => handleKeyClick('π')}>π</button>

            {/* Row 5 */}
            <button type="button" className="calc-key calc-key--num calc-key--wide" onClick={() => handleKeyClick('0')}>0</button>
            <button type="button" className="calc-key calc-key--num" onClick={() => handleKeyClick('00')}>00</button>
            <button type="button" className="calc-key calc-key--num" onClick={() => handleKeyClick('.')}>.</button>
            <button type="button" className="calc-key calc-key--equals calc-key--wide" onClick={() => handleKeyClick('=')}>=</button>
          </div>
        </div>

        {/* Right: Calculation History */}
        <div className="calculator-history-card">
          <div className="calculator-history-header">
            <h3 className="calculator-history-title">Recent Calculations</h3>
            <span className="calculator-history-count">{history.length} items</span>
          </div>

          <div className="calculator-history-list">
            {history.length === 0 ? (
              <div className="calculator-history-empty">
                <span className="calculator-empty-icon">📝</span>
                <p>No calculation history yet</p>
                <span className="calculator-empty-hint">Calculations will appear here as you solve math expressions.</span>
              </div>
            ) : (
              history.map((item) => (
                <div
                  key={item.id}
                  className="calculator-history-item"
                  onClick={() => {
                    setExpression(item.expression);
                    setResult(item.result);
                  }}
                  title="Click to load into calculator"
                >
                  <div className="calculator-history-expr">{item.expression}</div>
                  <div className="calculator-history-res">
                    = {item.result}
                    <span className="calculator-history-time">{item.timestamp}</span>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
