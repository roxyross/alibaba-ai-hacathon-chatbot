import { describe, it, expect, vi } from 'vitest';
import { renderToString } from 'react-dom/server';
import { RoxyCommandBar } from '../RoxyCommandBar';
import { I18nProvider } from '../../../i18n';

describe('Phase 20: Universal Roxy Command Experience — RoxyCommandBar', () => {
  it('renders command palette when open is true', () => {
    const html = renderToString(
      <I18nProvider>
        <RoxyCommandBar
          isOpen={true}
          onClose={vi.fn()}
          onNavigateView={vi.fn()}
          onSendChatQuery={vi.fn()}
          onOpenNewTask={vi.fn()}
          onEnterCowork={vi.fn()}
          onStartVoice={vi.fn()}
        />
      </I18nProvider>
    );

    expect(html).toContain('ROXY COMMAND');
    expect(html).toContain('v2.0 Universal');
    expect(html).toContain('Ask Roxy anything, launch a task, or open any studio');
    expect(html).toContain('New Task');
    expect(html).toContain('Cowork Mode');
    expect(html).toContain('Voice Session');
    expect(html).toContain('Device Hub');
  });

  it('renders nothing when isOpen is false', () => {
    const html = renderToString(
      <I18nProvider>
        <RoxyCommandBar
          isOpen={false}
          onClose={vi.fn()}
          onNavigateView={vi.fn()}
          onSendChatQuery={vi.fn()}
          onOpenNewTask={vi.fn()}
          onEnterCowork={vi.fn()}
          onStartVoice={vi.fn()}
        />
      </I18nProvider>
    );

    expect(html).toBe('');
  });

  it('includes multilingual locale buttons for en, ur, and ar', () => {
    const html = renderToString(
      <I18nProvider>
        <RoxyCommandBar
          isOpen={true}
          onClose={vi.fn()}
          onNavigateView={vi.fn()}
          onSendChatQuery={vi.fn()}
          onOpenNewTask={vi.fn()}
          onEnterCowork={vi.fn()}
          onStartVoice={vi.fn()}
        />
      </I18nProvider>
    );

    expect(html).toContain('English');
    expect(html).toContain('اردو');
    expect(html).toContain('العربية');
  });
});
