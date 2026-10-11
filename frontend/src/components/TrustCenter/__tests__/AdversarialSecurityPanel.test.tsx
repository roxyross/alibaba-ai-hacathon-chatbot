import { describe, it, expect } from 'vitest';
import { renderToString } from 'react-dom/server';
import { AdversarialSecurityPanel } from '../AdversarialSecurityPanel';

describe('Phase 24: Adversarial Security Panel Component Suite', () => {
  const mockProps = {
    accessToken: 'mock_security_token',
  };

  it('renders Adversarial Security Panel header and audit controls', () => {
    const html = renderToString(<AdversarialSecurityPanel {...mockProps} />);
    expect(html).toContain('Adversarial Security Defense Suite');
    expect(html).toContain('Run Full Security Audit');
    expect(html).toContain('Prompt, Command, SQL, Path, SSRF');
  });

  it('renders subtabs for all defense testing categories', () => {
    const html = renderToString(<AdversarialSecurityPanel {...mockProps} />);
    expect(html).toContain('Prompt Injection &amp; Jailbreak');
    expect(html).toContain('Mutation Fuzzer');
    expect(html).toContain('Injection Defenses');
    expect(html).toContain('RBAC &amp; IDOR Isolation');
  });

  it('renders prompt injection analyzer and preset attack vectors', () => {
    const html = renderToString(<AdversarialSecurityPanel {...mockProps} />);
    expect(html).toContain('Prompt Injection &amp; Jailbreak Analyzer');
    expect(html).toContain('Test Attack Vectors:');
    expect(html).toContain('Scan Prompt Vector');
  });
});
