import { describe, it, expect, vi } from 'vitest';
import { renderToString } from 'react-dom/server';
import { NewTaskModal } from '../NewTaskModal';
import type { DeviceInfo } from '../../DeviceHub';

describe('Phase 20: NewTaskModal Component Suite', () => {
  const mockDevices: DeviceInfo[] = [
    {
      id: 'dev_mock_host',
      user_id: 'usr_test',
      device_name: 'Workstation Host (Windows)',
      device_type: 'desktop',
      os_platform: 'windows',
      os_version: '11 Pro',
      architecture: 'x86_64',
      hostname: 'DESKTOP-ROXY',
      ip_address: '127.0.0.1',
      status: 'online',
      is_current_host: true,
      capabilities: ['screen_capture', 'app_discovery'],
      telemetry: {},
    },
  ];

  it('renders task configuration modal with title, templates, and execution modes', () => {
    const html = renderToString(
      <NewTaskModal
        isOpen={true}
        onClose={vi.fn()}
        devices={mockDevices}
        onSubmitTask={vi.fn()}
      />
    );

    expect(html).toContain('Launch New ROXY Task');
    expect(html).toContain('Full-Stack Web App Development');
    expect(html).toContain('Cross-Device Security &amp; Permission Audit');
    expect(html).toContain('Autonomous Operator');
    expect(html).toContain('Supervised / Guided');
    expect(html).toContain('Workstation Host (Windows)');
    expect(html).toContain('Launch Autonomous Task');
  });

  it('renders nothing when isOpen is false', () => {
    const html = renderToString(
      <NewTaskModal
        isOpen={false}
        onClose={vi.fn()}
        devices={mockDevices}
        onSubmitTask={vi.fn()}
      />
    );

    expect(html).toBe('');
  });
});
