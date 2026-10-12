import { describe, it, expect, vi } from 'vitest';
import { renderToString } from 'react-dom/server';
import { CodeStudioIDE } from '../CodeStudioIDE';
import { ReminderAlarmToast } from '../../Reminders/ReminderAlarmToast';

describe('ROXY Code Studio / Full IDE Component Suite', () => {
  it('renders top bar, project selector, activity bar, editor tabs, agent panel, and bottom tabs', () => {
    const html = renderToString(
      <CodeStudioIDE
        accessToken="mock_token"
        onBack={vi.fn()}
        onSendToChat={vi.fn()}
      />
    );

    // Top Bar & Brand
    expect(html).toContain('Code Studio');
    expect(html).toContain('ROXY Workspace (Current)');
    expect(html).toContain('Command Palette');
    expect(html).toContain('Roxy Agent');
    expect(html).toContain('Test');
    expect(html).toContain('Run');

    // Activity Bar
    expect(html).toContain('Explorer');
    expect(html).toContain('MCP &amp; Plugins');

    // Right Coding Agent
    expect(html).toContain('Roxy Coding Agent');
    expect(html).toContain('Connected');

    // Bottom Panel Tabs
    expect(html).toContain('TERMINAL');
    expect(html).toContain('PROBLEMS');
    expect(html).toContain('TEST RESULTS');
    expect(html).toContain('WEB DEV PREVIEW');
  });

  it('renders ReminderAlarmToast container without crashes', () => {
    const html = renderToString(
      <ReminderAlarmToast accessToken="mock_token" />
    );

    expect(html).toBeDefined();
  });
});
