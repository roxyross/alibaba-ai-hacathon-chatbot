import { describe, it, expect } from 'vitest';
import { renderToString } from 'react-dom/server';
import { TestingMatrixPanel } from '../TestingMatrixPanel';

describe('Phase 23: Testing Matrix Panel Component Suite', () => {
  const mockProps = {
    authHeaders: { Authorization: 'Bearer mock_token' },
    apiBase: '/api/v1',
  };

  it('renders Testing Matrix Panel header and run triggers', () => {
    const html = renderToString(<TestingMatrixPanel {...mockProps} />);
    expect(html).toContain('Multi-Platform Testing Matrix');
    expect(html).toContain('Desktop, Mobile (Android/iOS), Cloud Workers, and MCP Connectors');
    expect(html).toContain('Run Full Testing Matrix');
  });

  it('renders all four platform pillar cards', () => {
    const html = renderToString(<TestingMatrixPanel {...mockProps} />);
    expect(html).toContain('DESKTOP');
    expect(html).toContain('MOBILE');
    expect(html).toContain('CLOUD');
    expect(html).toContain('MCP');
  });

  it('renders cross-platform scenario execution panel', () => {
    const html = renderToString(<TestingMatrixPanel {...mockProps} />);
    expect(html).toContain('Cross-Platform Multi-Hop E2E Scenarios');
    expect(html).toContain('Execute Scenario');
  });
});
