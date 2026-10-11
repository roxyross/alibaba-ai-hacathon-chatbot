import { describe, it, expect } from 'vitest';
import { renderToString } from 'react-dom/server';
import { ProductionExitGatePanel } from '../ProductionExitGatePanel';

describe('Phase 25: Production Exit Gate Panel Component Suite', () => {
  const mockProps = {
    accessToken: 'mock_exit_gate_token',
  };

  it('renders Production Exit Gate banner, score gauge, and audit controls', () => {
    const html = renderToString(<ProductionExitGatePanel {...mockProps} />);
    expect(html).toContain('Production Readiness &amp; Final Exit Gate Audit');
    expect(html).toContain('Strict 7-Point Exit Checklist');
    expect(html).toContain('Re-Evaluate Gate');
    expect(html).toContain('View Certificate');
    expect(html).toContain('/ 700 pts');
  });

  it('renders KPI metric overview cards for Zero-Mock, AST Hygiene, and Packaging', () => {
    const html = renderToString(<ProductionExitGatePanel {...mockProps} />);
    expect(html).toContain('Zero-Mock Doctrine');
    expect(html).toContain('Code Hygiene &amp; AST');
    expect(html).toContain('Packaging &amp; Artifacts');
    expect(html).toContain('Exit Gate Checkpoints');
  });

  it('renders all three subtabs for checklist, zero-mock audit, and packaging', () => {
    const html = renderToString(<ProductionExitGatePanel {...mockProps} />);
    expect(html).toContain('7-Point Readiness Checklist');
    expect(html).toContain('Zero-Mock AST Audit');
    expect(html).toContain('Packaging &amp; Containers');
  });

  it('renders checklist table headers with verification proof column', () => {
    const html = renderToString(<ProductionExitGatePanel {...mockProps} />);
    expect(html).toContain('Gate ID');
    expect(html).toContain('Checkpoint &amp; Category');
    expect(html).toContain('Status');
    expect(html).toContain('Score');
    expect(html).toContain('Verification Proof');
  });
});
