import { describe, it, expect, vi } from 'vitest';
import { renderToString } from 'react-dom/server';
import { ModelPicker } from '../ModelPicker';

// Mock useModels to return empty providers list (so it uses DEFAULT_PROVIDERS)
vi.mock('../useModels', () => ({
  useModels: () => ({
    providers: [],
    loading: false,
    error: null,
    reload: vi.fn(),
  }),
}));

describe('ModelPicker — Gemini 4 Argon Default & Gemini 3.8 / Grok Preservation', () => {
  it('renders with gemini-4-argon as the fallback default selected value', () => {
    const handleChange = vi.fn();
    const html = renderToString(<ModelPicker value={null} onChange={handleChange} />);

    // Value should default to gemini/gemini-4-argon
    expect(html).toContain('value="gemini/gemini-4-argon"');
  });

  it('preserves gemini-3.8-flash and gemini-3.6-flash when explicitly provided', () => {
    const handleChange = vi.fn();
    const html = renderToString(
      <ModelPicker
        value={{ provider: 'gemini', model: 'gemini-3.6-flash' }}
        onChange={handleChange}
      />
    );

    // Selected value must reflect gemini-3.6-flash
    expect(html).toContain('value="gemini/gemini-3.6-flash"');
    expect(html).toContain('Gemini 3.6 Flash');
  });

  it('renders all baseline Gemini models with gemini-4-argon as primary', () => {
    const handleChange = vi.fn();
    const html = renderToString(
      <ModelPicker
        value={{ provider: 'gemini', model: 'gemini-4-argon' }}
        onChange={handleChange}
      />
    );

    const expectedGeminiOptions = [
      'value="gemini/gemini-4-argon"',
      'value="gemini/gemini-3.8-flash"',
      'value="gemini/gemini-3.6-flash"',
      'value="gemini/gemini-3.7-flash"',
      'value="gemini/gemini-3.1-flash"',
      'value="gemini/gemini-2.5-flash"',
      'value="gemini/gemini-2.0-flash"',
      'value="gemini/gemini-1.5-pro"',
      'value="gemini/gemini-1.5-flash"',
    ];

    for (const opt of expectedGeminiOptions) {
      expect(html).toContain(opt);
    }
  });

  it('renders all baseline Grok models under xAI / Groq optgroup including grok-4.7', () => {
    const handleChange = vi.fn();
    const html = renderToString(
      <ModelPicker
        value={{ provider: 'gemini', model: 'gemini-4-argon' }}
        onChange={handleChange}
      />
    );

    expect(html).toContain('label="xAI / Groq"');

    const expectedGrokOptions = [
      'value="grok/grok-4.7"',
      'value="grok/qwen/qwen3.8-27b"',
      'value="grok/openai/gpt-oss-120b"',
      'value="grok/qwen/qwen3.6-27b"',
      'value="grok/grok-3"',
      'value="grok/grok-3-mini"',
      'value="grok/grok-2"',
      'value="grok/grok-2-vision-1212"',
      'value="grok/grok-beta"',
      'value="grok/llama-3.3-70b-versatile"',
      'value="grok/mixtral-8x7b-32768"',
    ];

    for (const opt of expectedGrokOptions) {
      expect(html).toContain(opt);
    }
  });

  it('ensures gemini-4-argon is first and gemini-3.8-flash is second under Google Gemini group', () => {
    const handleChange = vi.fn();
    const html = renderToString(
      <ModelPicker
        value={{ provider: 'gemini', model: 'gemini-4-argon' }}
        onChange={handleChange}
      />
    );

    const geminiGroupIdx = html.indexOf('label="Google Gemini"');
    const gemini4Idx = html.indexOf('value="gemini/gemini-4-argon"');
    const gemini38Idx = html.indexOf('value="gemini/gemini-3.8-flash"');
    const gemini36Idx = html.indexOf('value="gemini/gemini-3.6-flash"');

    expect(geminiGroupIdx).toBeGreaterThan(-1);
    expect(gemini4Idx).toBeGreaterThan(geminiGroupIdx);
    expect(gemini38Idx).toBeGreaterThan(gemini4Idx);
    expect(gemini36Idx).toBeGreaterThan(gemini38Idx);
  });
});
