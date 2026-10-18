import { describe, it, expect, vi } from 'vitest';
import { renderToString } from 'react-dom/server';
import { CoworkWorkspace } from '../CoworkWorkspace';

describe('Phase 20: CoworkWorkspace Component Suite', () => {
  it('renders cowork header with status badge, surface switcher tabs, and split panes', () => {
    const html = renderToString(
      <CoworkWorkspace
        accessToken="mock_token"
        onExitCowork={vi.fn()}
        onSendToChat={vi.fn()}
        chatChildren={<div data-testid="chat-copilot">Active Chat Window</div>}
      />
    );

    expect(html).toContain('Collaborative Cowork Active');
    expect(html).toContain('Code Workspace');
    expect(html).toContain('Web Workspace');
    expect(html).toContain('Device &amp; Screen');
    expect(html).toContain('Task Plan');
    expect(html).toContain('Exit Cowork');
    expect(html).toContain('Active Chat Window');
  });
});
