import React, { useState, useEffect, useRef } from 'react';
import { VoiceInputControl, speakVoiceText } from '../common/VoiceInputControl';
import './Calculator.css';

export function parseSpokenMath(spoken: string): string {
  if (!spoken) return '';
  let s = spoken.trim();

  // 1. Convert Persian / Urdu / Arabic digits (۰-۹) to standard (0-9)
  s = s.replace(/[\u06F0-\u06F9]/g, (d) => String(d.charCodeAt(0) - 0x06F0));
  s = s.replace(/[\u0660-\u0669]/g, (d) => String(d.charCodeAt(0) - 0x0660));

  // 2. Convert Devanagari / Hindi digits (०-९) to standard (0-9)
  s = s.replace(/[\u0966-\u096F]/g, (d) => String(d.charCodeAt(0) - 0x0966));

  // 3. Lowercase for word matching
  s = s.toLowerCase();

  // 4. Normalize English / Roman Urdu / Hindi spoken number words to digits
  const wordToNumber: Record<string, string> = {
    zero: '0', sifar: '0', shunya: '0',
    one: '1', ek: '1',
    two: '2', do: '2',
    three: '3', teen: '3',
    four: '4', char: '4', chaar: '4',
    five: '5', paanch: '5', panch: '5',
    six: '6', chhe: '6', che: '6',
    seven: '7', saat: '7',
    eight: '8', aath: '8',
    nine: '9', nau: '9', no: '9',
    ten: '10', das: '10',
    eleven: '11', gyarah: '11',
    twelve: '12', barah: '12',
    thirteen: '13', terah: '13',
    fourteen: '14', chaudah: '14',
    fifteen: '15', pandrah: '15',
    sixteen: '16', solah: '16',
    seventeen: '17', satrah: '17',
    eighteen: '18', atharah: '18',
    nineteen: '19', unnis: '19',
    twenty: '20', bees: '20',
    thirty: '30', tees: '30',
    forty: '40', chalis: '40',
    fifty: '50', pachas: '50', pachaas: '50',
    sixty: '60', saath: '60',
    seventy: '70', sattar: '70',
    eighty: '80', assi: '80',
    ninety: '90', nabbe: '90',
    hundred: '100', sau: '100',
    thousand: '1000', hazar: '1000', hazaar: '1000',
  };

  for (const [w, num] of Object.entries(wordToNumber)) {
    const reg = new RegExp(`\\b${w}\\b`, 'gi');
    s = s.replace(reg, num);
  }

  // 5. Replace mathematical operation phrases (English, Urdu, Hindi, Scripts)
  s = s
    // Addition
    .replace(/\b(plus|jamah|jod|dhan|aur)\b/gi, '+')
    .replace(/[جمع\u091C\u094B\u095C\u0927\u0928\u0914\u0930]/g, (match) => {
      if (match === 'جمع' || match === 'اور') return '+';
      return match;
    })
    .replace(/(जोड़|धन|और)/g, '+')

    // Subtraction
    .replace(/\b(minus|manfi|ghatana|ghatao|rin)\b/gi, '-')
    .replace(/(منفی|घटाना|घटाव|ऋण)/g, '-')

    // Multiplication
    .replace(/\b(times|multiplied by|into|zarab|guna)\b/gi, '*')
    .replace(/\bx\b/gi, '*')
    .replace(/(ضرب|गुणा)/g, '*')

    // Division
    .replace(/\b(divided by|divide|over|taqseem|bhaag|bhag)\b/gi, '/')
    .replace(/(تقسیم|भाग)/g, '/')

    // Power
    .replace(/\b(to the power of|power|ki taqat|ki ghaat)\b/gi, '^')
    .replace(/(کی طاقت|की घात)/g, '^')

    // Square root
    .replace(/\b(square root of|sqrt|root of|jazar|vargmool)\b/gi, '√')
    .replace(/(جذر|वर्गमूल)/g, '√')

    // Percentage
    .replace(/\b(percent of|percentage of|percent|percentage|feesad|pratishat)\b/gi, '% *')
    .replace(/(فیصد|प्रतिशत)/g, '% *');

  // 6. Strip filler / equality / query phrases that speech recognizers append:
  // e.g. "equals to", "equal to", "equals", "equal", "= to", "=is", "is to", "is", "to", "total", etc.
  s = s
    .replace(/\b(what is|calculate|solve|batao|bataiye|kya hai|kya hoga|kitna hai|kitna hoga|kitna hua|kitna)\b/gi, '')
    .replace(/(کیا ہے|کتنا ہوگا|کتنا ہوا|کتنا ہے|بتاؤ|बताओ|क्या है|कितना होगा|कितना हुआ|कितना है)/g, '')
    .replace(/\b(is equal to|equals to|equal to|equals|equal|is to|=to|=is|total of|sum of|result of|total|result|answer)\b/gi, '')
    .replace(/\b(barabar hai|barabar)\b/gi, '')
    .replace(/(برابر ہے|برابر|बराबर है|बराबर)/g, '')
    // Also remove trailing or stray words "is", "to", "ka", etc.
    .replace(/\b(is|to|ka|ki|ke|ko|se)\b/gi, '')
    .replace(/(کا|کی|کے|کو|سے|का|की|के|को|से)/g, '')
    .replace(/[=?:\!]/g, '')
    .trim();

  // 7. Clean up double spaces or spaces around operators
  s = s.replace(/\s*([+\-*/^√%])\s*/g, ' $1 ').replace(/\s+/g, ' ').trim();

  // If square root has space, e.g. "√ 25" -> "√25"
  s = s.replace(/√\s+/g, '√');

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

  // Automatically parse, evaluate, and speak math results aloud
  const evaluateAndSpeak = async (rawSpoken: string) => {
    const parsed = parseSpokenMath(rawSpoken);
    if (!parsed) return;
    setExpression(parsed);
    setErrorMessage(null);

    // 1. Try client-side evaluation first
    try {
      const computed = calculateClient(parsed);
      const resStr = Number.isInteger(computed)
        ? computed.toString()
        : computed.toFixed(6).replace(/\.?0+$/, '');

      setResult(resStr);
      setLastSource('client');

      const newItem: HistoryItem = {
        id: Date.now().toString(),
        expression: parsed,
        result: resStr,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        source: 'client',
      };
      setHistory((prev) => [newItem, ...prev.filter((h) => h.expression !== parsed)]);

      // Speak answer aloud
      void speakVoiceText(`${parsed} equals ${resStr}`);
      return;
    } catch {
      // Proceed to backend Python evaluation
    }

    // 2. Backend Python AST evaluation
    setIsLoadingBackend(true);
    try {
      const pythonExpr = parsed
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
        expression: parsed,
        result: resVal,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        source: 'backend',
      };
      setHistory((prev) => [newItem, ...prev.filter((h) => h.expression !== parsed)]);

      // Speak answer aloud
      void speakVoiceText(`${parsed} equals ${resVal}`);
    } catch (err) {
      setErrorMessage(`Evaluation failed: ${err instanceof Error ? err.message : 'Unknown error'}`);
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
              void evaluateAndSpeak(text);
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
                showReadAloud={Boolean(result)}
                readAloudText={result ? `${expression} equals ${result}` : ''}
                onTranscript={(text) => {
                  void evaluateAndSpeak(text);
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
