import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Layers,
  ArrowLeft,
  Plus,
  Trash2,
  Sparkles,
  RefreshCw,
  CheckCircle2,
  XCircle,
  AlertCircle,
  FileCode,
  Globe,
  Radio,
  Play,
  Zap,
  Cpu,
  X,
  ChevronRight,
} from 'lucide-react';
import './ConnectorsHub.css';

const rawApiBase =
  (import.meta as { env: { VITE_API_BASE?: string } }).env.VITE_API_BASE ??
  '/api/v1';
const API_BASE = rawApiBase.endsWith('/api/v1')
  ? rawApiBase
  : `${rawApiBase.replace(/\/+$/, '')}/api/v1`;

export type HubTab = 'connectors' | 'mcp' | 'skills' | 'openapi';

export interface ConnectorTypeInfo {
  type: string;
  title: string;
  description: string;
  auth_methods: string[];
  default_config: Record<string, any>;
  required_credentials: string[];
  supported_actions: string[];
  icon?: string;
}

export interface ConnectorItem {
  id: string;
  connector_type: string;
  name: string;
  description?: string;
  auth_type: string;
  status: string;
  last_health_check_at?: string | null;
  error_message?: string | null;
  config: Record<string, any>;
  credentials: Record<string, string>;
  action_count: number;
  created_at?: string;
  updated_at?: string;
}

export interface MCPServerItem {
  id: string;
  name: string;
  description?: string;
  transport: string;
  endpoint_url?: string;
  command?: string;
  arguments: string[];
  env: Record<string, string>;
  status: string;
  protocol_version: string;
  discovered_tools: Array<{ name: string; description?: string; input_schema?: any }>;
  discovered_resources: Array<{ uri: string; name: string; description?: string }>;
  discovered_prompts: Array<{ name: string; description?: string }>;
  last_synced_at?: string | null;
  error_message?: string | null;
}

export interface CustomSkillItem {
  id: string;
  name: string;
  skill_key: string;
  description: string;
  trigger_phrases: string[];
  parameters_schema: Record<string, any>;
  execution_type: 'prompt' | 'python_sandbox';
  code_or_prompt_template: string;
  risk_level: string;
  requires_confirmation: boolean;
  enabled: boolean;
  created_at?: string;
}

interface ConnectorsHubProps {
  accessToken: string | null;
  onBack: () => void;
  onSendToChat?: (text: string) => void;
}

export const ConnectorsHub: React.FC<ConnectorsHubProps> = ({
  accessToken,
  onBack,
  onSendToChat,
}) => {
  const [activeTab, setActiveTab] = useState<HubTab>('connectors');
  const [loading, setLoading] = useState(false);
  const [statusMessage, setStatusMessage] = useState<{ text: string; type: 'success' | 'error' | 'info' } | null>(null);

  // Data states
  const [catalogTypes, setCatalogTypes] = useState<ConnectorTypeInfo[]>([]);
  const [connectors, setConnectors] = useState<ConnectorItem[]>([]);
  const [mcpServers, setMcpServers] = useState<MCPServerItem[]>([]);
  const [customSkills, setCustomSkills] = useState<CustomSkillItem[]>([]);

  // Testing states
  const [testingConnectorId, setTestingConnectorId] = useState<string | null>(null);
  const [testResults, setTestResults] = useState<Record<string, { success: boolean; latency: number; message: string }>>({});
  const [syncingServerId, setSyncingServerId] = useState<string | null>(null);

  // Modals
  const [showAddConnectorModal, setShowAddConnectorModal] = useState(false);
  const [selectedCatalogType, setSelectedCatalogType] = useState<ConnectorTypeInfo | null>(null);
  const [connectorFormName, setConnectorFormName] = useState('');
  const [connectorFormDesc, setConnectorFormDesc] = useState('');
  const [connectorFormConfig, setConnectorFormConfig] = useState<Record<string, string>>({});
  const [connectorFormCreds, setConnectorFormCreds] = useState<Record<string, string>>({});

  // MCP Form
  const [showAddMcpModal, setShowAddMcpModal] = useState(false);
  const [mcpName, setMcpName] = useState('');
  const [mcpDesc, setMcpDesc] = useState('');
  const [mcpTransport, setMcpTransport] = useState<'sse' | 'stdio'>('sse');
  const [mcpEndpoint, setMcpEndpoint] = useState('');
  const [mcpCommand, setMcpCommand] = useState('');
  const [mcpArgs, setMcpArgs] = useState('');

  // OpenAPI Import Form
  const [openApiName, setOpenApiName] = useState('');
  const [openApiSpecUrl, setOpenApiSpecUrl] = useState('');
  const [openApiSpecJson, setOpenApiSpecJson] = useState('');
  const [openApiBaseUrl, setOpenApiBaseUrl] = useState('');
  const [openApiApiKey, setOpenApiApiKey] = useState('');
  const [importingOpenApi, setImportingOpenApi] = useState(false);

  // Custom Skill Form
  const [showAddSkillModal, setShowAddSkillModal] = useState(false);
  const [skillName, setSkillName] = useState('');
  const [skillKey, setSkillKey] = useState('');
  const [skillDesc, setSkillDesc] = useState('');
  const [skillExecType, setSkillExecType] = useState<'prompt' | 'python_sandbox'>('prompt');
  const [skillTemplate, setSkillTemplate] = useState('Draft an update about {topic} for team {team}');
  const [skillRisk, setSkillRisk] = useState<'low' | 'medium' | 'high'>('low');
  const [skillConfirm, setSkillConfirm] = useState(false);

  // Skill runner modal
  const [runningSkill, setRunningSkill] = useState<CustomSkillItem | null>(null);
  const [skillArgsInput, setSkillArgsInput] = useState('{"topic": "Q3 Launch", "team": "Marketing"}');
  const [skillExecResult, setSkillExecResult] = useState<any>(null);
  const [skillExecuting, setSkillExecuting] = useState(false);

  const authHeaders = useMemo(() => {
    return {
      'Content-Type': 'application/json',
      ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
    };
  }, [accessToken]);

  // Load all initial data
  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      // 1. Catalog types
      const typesRes = await fetch(`${API_BASE}/connectors/types`, { headers: authHeaders });
      if (typesRes.ok) {
        const typesData = await typesRes.json();
        setCatalogTypes(typesData);
      }

      // 2. User Connectors
      const connRes = await fetch(`${API_BASE}/connectors`, { headers: authHeaders });
      if (connRes.ok) {
        const connData = await connRes.json();
        setConnectors(connData);
      }

      // 3. MCP Servers
      const mcpRes = await fetch(`${API_BASE}/mcp/servers`, { headers: authHeaders });
      if (mcpRes.ok) {
        const mcpData = await mcpRes.json();
        setMcpServers(mcpData);
      }

      // 4. Custom Skills
      const skillRes = await fetch(`${API_BASE}/skills/custom`, { headers: authHeaders });
      if (skillRes.ok) {
        const skillData = await skillRes.json();
        setCustomSkills(skillData);
      }
    } catch (err: any) {
      console.error('Failed to load Connectors & MCP data:', err);
    } finally {
      setLoading(false);
    }
  }, [authHeaders]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // Handler: Test Connector
  const handleTestConnector = async (id: string) => {
    setTestingConnectorId(id);
    try {
      const res = await fetch(`${API_BASE}/connectors/${id}/test`, {
        method: 'POST',
        headers: authHeaders,
      });
      const data = await res.json();
      setTestResults((prev) => ({
        ...prev,
        [id]: {
          success: data.success,
          latency: data.latency_ms,
          message: data.message,
        },
      }));
      // Refresh list to update health status
      const ref = await fetch(`${API_BASE}/connectors`, { headers: authHeaders });
      if (ref.ok) setConnectors(await ref.json());
    } catch (err: any) {
      setTestResults((prev) => ({
        ...prev,
        [id]: { success: false, latency: 0, message: err.message || 'Test failed' },
      }));
    } finally {
      setTestingConnectorId(null);
    }
  };

  // Handler: Delete Connector
  const handleDeleteConnector = async (id: string) => {
    if (!window.confirm('Are you sure you want to remove this connector? Associated tools will be unregistered.')) return;
    try {
      const res = await fetch(`${API_BASE}/connectors/${id}`, {
        method: 'DELETE',
        headers: authHeaders,
      });
      if (res.ok) {
        setConnectors((prev) => prev.filter((c) => c.id !== id));
        setStatusMessage({ text: 'Connector deleted successfully', type: 'info' });
      }
    } catch (err: any) {
      setStatusMessage({ text: err.message || 'Failed to delete connector', type: 'error' });
    }
  };

  // Handler: Create Connector
  const handleCreateConnector = async () => {
    if (!selectedCatalogType || !connectorFormName.trim()) return;
    try {
      const payload = {
        connector_type: selectedCatalogType.type,
        name: connectorFormName.trim(),
        description: connectorFormDesc.trim(),
        auth_type: selectedCatalogType.auth_methods[0] || 'api_key',
        config: connectorFormConfig,
        credentials: connectorFormCreds,
      };

      const res = await fetch(`${API_BASE}/connectors`, {
        method: 'POST',
        headers: authHeaders,
        body: JSON.stringify(payload),
      });

      if (res.ok) {
        setShowAddConnectorModal(false);
        setSelectedCatalogType(null);
        setConnectorFormName('');
        setConnectorFormDesc('');
        setConnectorFormConfig({});
        setConnectorFormCreds({});
        setStatusMessage({ text: 'Connector configured and actions synced!', type: 'success' });
        fetchData();
      } else {
        const err = await res.json();
        alert(err.detail || 'Failed to create connector');
      }
    } catch (err: any) {
      alert(err.message || 'Creation error');
    }
  };

  // Handler: Import OpenAPI
  const handleImportOpenApi = async () => {
    if (!openApiName.trim() || (!openApiSpecUrl.trim() && !openApiSpecJson.trim())) {
      alert('Please provide a name and either a Spec URL or JSON specification.');
      return;
    }
    setImportingOpenApi(true);
    try {
      const payload: any = {
        name: openApiName.trim(),
        base_url: openApiBaseUrl.trim() || undefined,
        api_key: openApiApiKey.trim() || undefined,
      };
      if (openApiSpecUrl.trim()) payload.spec_url = openApiSpecUrl.trim();
      if (openApiSpecJson.trim()) payload.spec_json = openApiSpecJson.trim();

      const res = await fetch(`${API_BASE}/connectors/openapi/import`, {
        method: 'POST',
        headers: authHeaders,
        body: JSON.stringify(payload),
      });

      if (res.ok) {
        const data = await res.json();
        setStatusMessage({
          text: `Imported '${data.name}'! Generated ${data.tools_generated} dynamic agent tools.`,
          type: 'success',
        });
        setOpenApiName('');
        setOpenApiSpecUrl('');
        setOpenApiSpecJson('');
        setOpenApiBaseUrl('');
        setOpenApiApiKey('');
        setActiveTab('connectors');
        fetchData();
      } else {
        const err = await res.json();
        alert(err.detail || 'Import failed');
      }
    } catch (err: any) {
      alert(err.message || 'Import error');
    } finally {
      setImportingOpenApi(false);
    }
  };

  // Handler: Create MCP Server
  const handleCreateMcp = async () => {
    if (!mcpName.trim()) return;
    try {
      const argsList = mcpArgs
        .split(' ')
        .map((s) => s.trim())
        .filter(Boolean);

      const payload = {
        name: mcpName.trim(),
        description: mcpDesc.trim(),
        transport: mcpTransport,
        endpoint_url: mcpTransport === 'sse' ? mcpEndpoint.trim() : undefined,
        command: mcpTransport === 'stdio' ? mcpCommand.trim() : undefined,
        arguments: argsList,
        env: {},
      };

      const res = await fetch(`${API_BASE}/mcp/servers`, {
        method: 'POST',
        headers: authHeaders,
        body: JSON.stringify(payload),
      });

      if (res.ok) {
        setShowAddMcpModal(false);
        setMcpName('');
        setMcpDesc('');
        setMcpEndpoint('');
        setMcpCommand('');
        setMcpArgs('');
        setStatusMessage({ text: 'MCP Server registered and tools discovered!', type: 'success' });
        fetchData();
      } else {
        const err = await res.json();
        alert(err.detail || 'Failed to register MCP server');
      }
    } catch (err: any) {
      alert(err.message || 'MCP creation error');
    }
  };

  // Handler: Sync MCP Server
  const handleSyncMcp = async (id: string) => {
    setSyncingServerId(id);
    try {
      const res = await fetch(`${API_BASE}/mcp/servers/${id}/sync`, {
        method: 'POST',
        headers: authHeaders,
      });
      if (res.ok) {
        const data = await res.json();
        setStatusMessage({
          text: `Synced '${data.server_name}': ${data.tools_count} tools, ${data.resources_count} resources discovered.`,
          type: 'success',
        });
        fetchData();
      } else {
        const err = await res.json();
        alert(err.detail || 'Sync failed');
      }
    } catch (err: any) {
      alert(err.message || 'Sync error');
    } finally {
      setSyncingServerId(null);
    }
  };

  // Handler: Delete MCP Server
  const handleDeleteMcp = async (id: string) => {
    if (!window.confirm('Delete this MCP server and unregister all its discovered tools?')) return;
    try {
      const res = await fetch(`${API_BASE}/mcp/servers/${id}`, {
        method: 'DELETE',
        headers: authHeaders,
      });
      if (res.ok) {
        setMcpServers((prev) => prev.filter((s) => s.id !== id));
        setStatusMessage({ text: 'MCP server removed', type: 'info' });
      }
    } catch (err: any) {
      alert(err.message || 'Failed to delete MCP server');
    }
  };

  // Handler: Create Custom Skill
  const handleCreateSkill = async () => {
    if (!skillName.trim() || !skillKey.trim() || !skillTemplate.trim()) return;
    try {
      const payload = {
        name: skillName.trim(),
        skill_key: skillKey.trim(),
        description: skillDesc.trim(),
        execution_type: skillExecType,
        code_or_prompt_template: skillTemplate.trim(),
        risk_level: skillRisk,
        requires_confirmation: skillConfirm,
      };

      const res = await fetch(`${API_BASE}/skills/custom`, {
        method: 'POST',
        headers: authHeaders,
        body: JSON.stringify(payload),
      });

      if (res.ok) {
        setShowAddSkillModal(false);
        setSkillName('');
        setSkillKey('');
        setSkillDesc('');
        setStatusMessage({ text: 'Custom skill created and registered in Tool Registry!', type: 'success' });
        fetchData();
      } else {
        const err = await res.json();
        alert(err.detail || 'Failed to create skill');
      }
    } catch (err: any) {
      alert(err.message || 'Skill creation error');
    }
  };

  // Handler: Execute Custom Skill
  const handleRunCustomSkill = async () => {
    if (!runningSkill) return;
    setSkillExecuting(true);
    setSkillExecResult(null);
    try {
      let parsedArgs = {};
      try {
        parsedArgs = JSON.parse(skillArgsInput);
      } catch {
        parsedArgs = { input: skillArgsInput };
      }

      const res = await fetch(`${API_BASE}/skills/custom/${runningSkill.id}/execute`, {
        method: 'POST',
        headers: authHeaders,
        body: JSON.stringify({ arguments: parsedArgs }),
      });

      const data = await res.json();
      setSkillExecResult(data);
    } catch (err: any) {
      setSkillExecResult({ error: err.message || 'Execution failed' });
    } finally {
      setSkillExecuting(false);
    }
  };

  // Handler: Delete Custom Skill
  const handleDeleteSkill = async (id: string) => {
    if (!window.confirm('Delete this custom skill?')) return;
    try {
      const res = await fetch(`${API_BASE}/skills/custom/${id}`, {
        method: 'DELETE',
        headers: authHeaders,
      });
      if (res.ok) {
        setCustomSkills((prev) => prev.filter((s) => s.id !== id));
        setStatusMessage({ text: 'Custom skill removed', type: 'info' });
      }
    } catch (err: any) {
      alert(err.message || 'Failed to delete skill');
    }
  };

  return (
    <div className="connectors-hub">
      {/* Top Banner Header */}
      <header className="connectors-hub__header">
        <div className="connectors-hub__header-left">
          <button
            type="button"
            className="connectors-hub__back-btn"
            onClick={onBack}
            aria-label="Back to chat"
          >
            <ArrowLeft size={18} />
          </button>
          <div className="connectors-hub__title-wrap">
            <div className="connectors-hub__title-badge">
              <Layers size={18} className="connectors-hub__badge-icon" />
              <h1>Connectors & MCP Protocol Hub</h1>
            </div>
            <p className="connectors-hub__subtitle">
              Integrate enterprise APIs, remote Model Context Protocol (MCP) servers, OpenAPI specifications, and autonomous custom skills directly into Roxy's Tool Registry.
            </p>
          </div>
        </div>

        <div className="connectors-hub__header-actions">
          <button
            type="button"
            className="connectors-hub__refresh-btn"
            onClick={fetchData}
            disabled={loading}
            title="Refresh All"
          >
            <RefreshCw size={15} className={loading ? 'connectors-hub__spin' : ''} />
            <span>Refresh</span>
          </button>
        </div>
      </header>

      {/* Status banner */}
      {statusMessage && (
        <div className={`connectors-hub__toast connectors-hub__toast--${statusMessage.type}`}>
          {statusMessage.type === 'success' ? <CheckCircle2 size={16} /> : <AlertCircle size={16} />}
          <span>{statusMessage.text}</span>
          <button
            type="button"
            className="connectors-hub__toast-close"
            onClick={() => setStatusMessage(null)}
          >
            <X size={14} />
          </button>
        </div>
      )}

      {/* Navigation Tabs */}
      <div className="connectors-hub__tabs">
        <button
          type="button"
          className={`connectors-hub__tab ${activeTab === 'connectors' ? 'connectors-hub__tab--active' : ''}`}
          onClick={() => setActiveTab('connectors')}
        >
          <Zap size={16} />
          <span>Active Connectors ({connectors.length})</span>
        </button>
        <button
          type="button"
          className={`connectors-hub__tab ${activeTab === 'mcp' ? 'connectors-hub__tab--active' : ''}`}
          onClick={() => setActiveTab('mcp')}
        >
          <Cpu size={16} />
          <span>MCP Servers ({mcpServers.length})</span>
        </button>
        <button
          type="button"
          className={`connectors-hub__tab ${activeTab === 'openapi' ? 'connectors-hub__tab--active' : ''}`}
          onClick={() => setActiveTab('openapi')}
        >
          <Globe size={16} />
          <span>OpenAPI / Swagger Import</span>
        </button>
        <button
          type="button"
          className={`connectors-hub__tab ${activeTab === 'skills' ? 'connectors-hub__tab--active' : ''}`}
          onClick={() => setActiveTab('skills')}
        >
          <Sparkles size={16} />
          <span>Custom Skills ({customSkills.length})</span>
        </button>
      </div>

      {/* Main Content Area */}
      <main className="connectors-hub__body">
        {/* TAB 1: CONNECTORS */}
        {activeTab === 'connectors' && (
          <div className="connectors-hub__section">
            <div className="connectors-hub__section-header">
              <div>
                <h2>Enterprise & SaaS Connectors</h2>
                <p>Manage authenticated integrations. Each connector automatically bridges its live actions into the central Agent Tool Registry.</p>
              </div>
              <button
                type="button"
                className="connectors-hub__primary-btn"
                onClick={() => setShowAddConnectorModal(true)}
              >
                <Plus size={16} />
                <span>Add Connector</span>
              </button>
            </div>

            {connectors.length === 0 ? (
              <div className="connectors-hub__empty">
                <Radio size={36} className="connectors-hub__empty-icon" />
                <h3>No Connectors Configured Yet</h3>
                <p>Connect Google Workspace, GitHub, Slack, Notion, or custom Webhooks to give Roxy agentic superpowers.</p>
                <button
                  type="button"
                  className="connectors-hub__action-btn"
                  onClick={() => setShowAddConnectorModal(true)}
                >
                  Configure Your First Connector
                </button>
              </div>
            ) : (
              <div className="connectors-hub__grid">
                {connectors.map((c) => {
                  const test = testResults[c.id];
                  const isTesting = testingConnectorId === c.id;
                  return (
                    <div key={c.id} className="connectors-card">
                      <div className="connectors-card__header">
                        <div className="connectors-card__title-box">
                          <span className="connectors-card__badge-type">{c.connector_type.toUpperCase()}</span>
                          <h3 className="connectors-card__title">{c.name}</h3>
                        </div>
                        <span className={`connectors-card__status connectors-card__status--${c.status}`}>
                          {c.status}
                        </span>
                      </div>

                      <p className="connectors-card__desc">{c.description || 'No description provided.'}</p>

                      <div className="connectors-card__meta">
                        <div className="connectors-card__meta-item">
                          <span className="connectors-card__meta-label">Actions:</span>
                          <span className="connectors-card__meta-value">{c.action_count} tools available</span>
                        </div>
                        <div className="connectors-card__meta-item">
                          <span className="connectors-card__meta-label">Auth:</span>
                          <span className="connectors-card__meta-value">{c.auth_type}</span>
                        </div>
                        {c.last_health_check_at && (
                          <div className="connectors-card__meta-item">
                            <span className="connectors-card__meta-label">Health:</span>
                            <span className="connectors-card__meta-value">
                              {new Date(c.last_health_check_at).toLocaleTimeString()}
                            </span>
                          </div>
                        )}
                      </div>

                      {test && (
                        <div className={`connectors-card__test-banner connectors-card__test-banner--${test.success ? 'success' : 'error'}`}>
                          {test.success ? <CheckCircle2 size={13} /> : <XCircle size={13} />}
                          <span>{test.message} ({test.latency}ms)</span>
                        </div>
                      )}

                      <div className="connectors-card__actions">
                        <button
                          type="button"
                          className="connectors-card__btn connectors-card__btn--test"
                          onClick={() => handleTestConnector(c.id)}
                          disabled={isTesting}
                        >
                          <RefreshCw size={13} className={isTesting ? 'connectors-hub__spin' : ''} />
                          <span>{isTesting ? 'Testing…' : 'Test Health'}</span>
                        </button>
                        <button
                          type="button"
                          className="connectors-card__btn connectors-card__btn--danger"
                          onClick={() => handleDeleteConnector(c.id)}
                          title="Delete Connector"
                        >
                          <Trash2 size={13} />
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}

        {/* TAB 2: MCP SERVERS */}
        {activeTab === 'mcp' && (
          <div className="connectors-hub__section">
            <div className="connectors-hub__section-header">
              <div>
                <h2>Model Context Protocol (MCP) Servers</h2>
                <p>Connect to remote or local MCP standard servers. Roxy discovers tools, resources, and prompts dynamically via JSON-RPC 2.0.</p>
              </div>
              <button
                type="button"
                className="connectors-hub__primary-btn"
                onClick={() => setShowAddMcpModal(true)}
              >
                <Plus size={16} />
                <span>Add MCP Server</span>
              </button>
            </div>

            {mcpServers.length === 0 ? (
              <div className="connectors-hub__empty">
                <Cpu size={36} className="connectors-hub__empty-icon" />
                <h3>No MCP Servers Connected</h3>
                <p>Connect your filesystem, PostgreSQL, GitHub, or custom tool servers using the standard MCP protocol (version 2024-11-05).</p>
                <button
                  type="button"
                  className="connectors-hub__action-btn"
                  onClick={() => setShowAddMcpModal(true)}
                >
                  Register MCP Server
                </button>
              </div>
            ) : (
              <div className="connectors-hub__grid">
                {mcpServers.map((s) => {
                  const isSyncing = syncingServerId === s.id;
                  return (
                    <div key={s.id} className="connectors-card">
                      <div className="connectors-card__header">
                        <div className="connectors-card__title-box">
                          <span className="connectors-card__badge-type">{s.transport.toUpperCase()}</span>
                          <h3 className="connectors-card__title">{s.name}</h3>
                        </div>
                        <span className={`connectors-card__status connectors-card__status--${s.status}`}>
                          {s.status}
                        </span>
                      </div>

                      <p className="connectors-card__desc">{s.description || 'MCP 2024-11-05 Server'}</p>

                      <div className="connectors-card__meta">
                        <div className="connectors-card__meta-item">
                          <span className="connectors-card__meta-label">Discovered Tools:</span>
                          <span className="connectors-card__meta-value">{s.discovered_tools.length}</span>
                        </div>
                        <div className="connectors-card__meta-item">
                          <span className="connectors-card__meta-label">Transport:</span>
                          <span className="connectors-card__meta-value">
                            {s.endpoint_url || s.command || 'stdio'}
                          </span>
                        </div>
                        {s.last_synced_at && (
                          <div className="connectors-card__meta-item">
                            <span className="connectors-card__meta-label">Last Synced:</span>
                            <span className="connectors-card__meta-value">
                              {new Date(s.last_synced_at).toLocaleTimeString()}
                            </span>
                          </div>
                        )}
                      </div>

                      {/* Tool Preview Chips */}
                      {s.discovered_tools.length > 0 && (
                        <div className="connectors-card__tools-chips">
                          {s.discovered_tools.slice(0, 4).map((t) => (
                            <span key={t.name} className="connectors-card__chip" title={t.description}>
                              {t.name}
                            </span>
                          ))}
                          {s.discovered_tools.length > 4 && (
                            <span className="connectors-card__chip connectors-card__chip--more">
                              +{s.discovered_tools.length - 4} more
                            </span>
                          )}
                        </div>
                      )}

                      <div className="connectors-card__actions">
                        <button
                          type="button"
                          className="connectors-card__btn connectors-card__btn--test"
                          onClick={() => handleSyncMcp(s.id)}
                          disabled={isSyncing}
                        >
                          <RefreshCw size={13} className={isSyncing ? 'connectors-hub__spin' : ''} />
                          <span>{isSyncing ? 'Syncing…' : 'Sync & Discover'}</span>
                        </button>
                        <button
                          type="button"
                          className="connectors-card__btn connectors-card__btn--danger"
                          onClick={() => handleDeleteMcp(s.id)}
                          title="Delete Server"
                        >
                          <Trash2 size={13} />
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}

        {/* TAB 3: OPENAPI SPEC IMPORT */}
        {activeTab === 'openapi' && (
          <div className="connectors-hub__section">
            <div className="connectors-hub__section-header">
              <div>
                <h2>Dynamic OpenAPI / Swagger Importer</h2>
                <p>Paste any REST OpenAPI 3.0 / Swagger JSON specification or provide a live URL. Roxy parses all path operations and compiles them into type-safe Agent Tools in real time.</p>
              </div>
            </div>

            <div className="connectors-hub__openapi-box">
              <div className="connectors-hub__form-group">
                <label>Connector Display Name *</label>
                <input
                  type="text"
                  placeholder="e.g. Stripe Billing API, Weather Service"
                  value={openApiName}
                  onChange={(e) => setOpenApiName(e.target.value)}
                />
              </div>

              <div className="connectors-hub__form-row">
                <div className="connectors-hub__form-group">
                  <label>OpenAPI Spec URL (optional)</label>
                  <input
                    type="url"
                    placeholder="https://api.example.com/openapi.json"
                    value={openApiSpecUrl}
                    onChange={(e) => setOpenApiSpecUrl(e.target.value)}
                  />
                </div>
                <div className="connectors-hub__form-group">
                  <label>Override Base URL (optional)</label>
                  <input
                    type="url"
                    placeholder="https://api.example.com/v1"
                    value={openApiBaseUrl}
                    onChange={(e) => setOpenApiBaseUrl(e.target.value)}
                  />
                </div>
              </div>

              <div className="connectors-hub__form-group">
                <label>API Key / Bearer Token (optional)</label>
                <input
                  type="password"
                  placeholder="Bearer token or API Secret"
                  value={openApiApiKey}
                  onChange={(e) => setOpenApiApiKey(e.target.value)}
                />
              </div>

              <div className="connectors-hub__form-group">
                <label>Or Paste Raw OpenAPI 3.0 JSON Specification:</label>
                <textarea
                  rows={8}
                  placeholder='{"openapi": "3.0.0", "info": {"title": "My API", "version": "1.0"}, "paths": {...}}'
                  value={openApiSpecJson}
                  onChange={(e) => setOpenApiSpecJson(e.target.value)}
                  className="connectors-hub__code-textarea"
                />
              </div>

              <button
                type="button"
                className="connectors-hub__primary-btn"
                onClick={handleImportOpenApi}
                disabled={importingOpenApi}
              >
                <FileCode size={16} />
                <span>{importingOpenApi ? 'Analyzing Spec & Compiling Tools…' : 'Import Specification & Generate Tools'}</span>
              </button>
            </div>
          </div>
        )}

        {/* TAB 4: CUSTOM SKILLS */}
        {activeTab === 'skills' && (
          <div className="connectors-hub__section">
            <div className="connectors-hub__section-header">
              <div>
                <h2>Autonomous Custom Skills</h2>
                <p>Define custom agent skills using prompt templates or sandboxed Python scripts. These are registered into the tool registry for autonomous execution.</p>
              </div>
              <button
                type="button"
                className="connectors-hub__primary-btn"
                onClick={() => setShowAddSkillModal(true)}
              >
                <Plus size={16} />
                <span>Create Custom Skill</span>
              </button>
            </div>

            {customSkills.length === 0 ? (
              <div className="connectors-hub__empty">
                <Sparkles size={36} className="connectors-hub__empty-icon" />
                <h3>No Custom Skills Defined</h3>
                <p>Create parameterized prompt templates or sandboxed scripts that Roxy can trigger autonomously during complex agent tasks.</p>
                <button
                  type="button"
                  className="connectors-hub__action-btn"
                  onClick={() => setShowAddSkillModal(true)}
                >
                  Create Your First Skill
                </button>
              </div>
            ) : (
              <div className="connectors-hub__grid">
                {customSkills.map((sk) => (
                  <div key={sk.id} className="connectors-card">
                    <div className="connectors-card__header">
                      <div className="connectors-card__title-box">
                        <span className="connectors-card__badge-type">{sk.execution_type.toUpperCase()}</span>
                        <h3 className="connectors-card__title">{sk.name}</h3>
                      </div>
                      <span className={`connectors-card__risk connectors-card__risk--${sk.risk_level}`}>
                        {sk.risk_level} risk
                      </span>
                    </div>

                    <p className="connectors-card__desc">{sk.description}</p>

                    <div className="connectors-card__code-preview">
                      <code>{sk.code_or_prompt_template.slice(0, 100)}...</code>
                    </div>

                    <div className="connectors-card__actions">
                      <button
                        type="button"
                        className="connectors-card__btn connectors-card__btn--test"
                        onClick={() => {
                          setRunningSkill(sk);
                          setSkillExecResult(null);
                        }}
                      >
                        <Play size={13} />
                        <span>Test Run</span>
                      </button>
                      <button
                        type="button"
                        className="connectors-card__btn connectors-card__btn--danger"
                        onClick={() => handleDeleteSkill(sk.id)}
                        title="Delete Skill"
                      >
                        <Trash2 size={13} />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </main>

      {/* MODAL 1: ADD CONNECTOR */}
      {showAddConnectorModal && (
        <div className="connectors-hub__modal-backdrop" onClick={() => setShowAddConnectorModal(false)}>
          <div className="connectors-hub__modal" onClick={(e) => e.stopPropagation()}>
            <div className="connectors-hub__modal-header">
              <h3>Add New Connector</h3>
              <button type="button" onClick={() => setShowAddConnectorModal(false)}>
                <X size={18} />
              </button>
            </div>

            <div className="connectors-hub__modal-body">
              {!selectedCatalogType ? (
                <div className="connectors-hub__catalog-list">
                  <p>Choose an enterprise provider to configure:</p>
                  {catalogTypes.map((cat) => (
                    <div
                      key={cat.type}
                      className="connectors-hub__catalog-item"
                      onClick={() => {
                        setSelectedCatalogType(cat);
                        setConnectorFormName(cat.title);
                        setConnectorFormDesc(cat.description);
                      }}
                    >
                      <div className="connectors-hub__catalog-info">
                        <h4>{cat.title}</h4>
                        <p>{cat.description}</p>
                      </div>
                      <ChevronRight size={18} />
                    </div>
                  ))}
                </div>
              ) : (
                <div className="connectors-hub__form">
                  <div className="connectors-hub__form-group">
                    <label>Connector Name *</label>
                    <input
                      type="text"
                      value={connectorFormName}
                      onChange={(e) => setConnectorFormName(e.target.value)}
                    />
                  </div>
                  <div className="connectors-hub__form-group">
                    <label>Description</label>
                    <input
                      type="text"
                      value={connectorFormDesc}
                      onChange={(e) => setConnectorFormDesc(e.target.value)}
                    />
                  </div>

                  {selectedCatalogType.required_credentials.map((cred) => (
                    <div key={cred} className="connectors-hub__form-group">
                      <label>{cred.replace(/_/g, ' ').toUpperCase()} *</label>
                      <input
                        type="password"
                        placeholder={`Enter ${cred}`}
                        value={connectorFormCreds[cred] || ''}
                        onChange={(e) =>
                          setConnectorFormCreds((prev) => ({ ...prev, [cred]: e.target.value }))
                        }
                      />
                    </div>
                  ))}

                  <div className="connectors-hub__modal-footer">
                    <button
                      type="button"
                      className="connectors-hub__btn-secondary"
                      onClick={() => setSelectedCatalogType(null)}
                    >
                      Back
                    </button>
                    <button
                      type="button"
                      className="connectors-hub__primary-btn"
                      onClick={handleCreateConnector}
                    >
                      Save & Sync Actions
                    </button>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* MODAL 2: ADD MCP SERVER */}
      {showAddMcpModal && (
        <div className="connectors-hub__modal-backdrop" onClick={() => setShowAddMcpModal(false)}>
          <div className="connectors-hub__modal" onClick={(e) => e.stopPropagation()}>
            <div className="connectors-hub__modal-header">
              <h3>Register Model Context Protocol (MCP) Server</h3>
              <button type="button" onClick={() => setShowAddMcpModal(false)}>
                <X size={18} />
              </button>
            </div>

            <div className="connectors-hub__modal-body">
              <div className="connectors-hub__form">
                <div className="connectors-hub__form-group">
                  <label>Server Name *</label>
                  <input
                    type="text"
                    placeholder="e.g. Postgres DB Explorer, Local Filesystem"
                    value={mcpName}
                    onChange={(e) => setMcpName(e.target.value)}
                  />
                </div>

                <div className="connectors-hub__form-group">
                  <label>Transport Type</label>
                  <select
                    value={mcpTransport}
                    onChange={(e) => setMcpTransport(e.target.value as any)}
                  >
                    <option value="sse">Server-Sent Events (SSE / HTTP)</option>
                    <option value="stdio">Local Process (stdio)</option>
                  </select>
                </div>

                {mcpTransport === 'sse' ? (
                  <div className="connectors-hub__form-group">
                    <label>SSE Endpoint URL *</label>
                    <input
                      type="url"
                      placeholder="http://localhost:3001/sse"
                      value={mcpEndpoint}
                      onChange={(e) => setMcpEndpoint(e.target.value)}
                    />
                  </div>
                ) : (
                  <>
                    <div className="connectors-hub__form-group">
                      <label>Command Process *</label>
                      <input
                        type="text"
                        placeholder="npx or python"
                        value={mcpCommand}
                        onChange={(e) => setMcpCommand(e.target.value)}
                      />
                    </div>
                    <div className="connectors-hub__form-group">
                      <label>Arguments (space-separated)</label>
                      <input
                        type="text"
                        placeholder="-y @modelcontextprotocol/server-everything"
                        value={mcpArgs}
                        onChange={(e) => setMcpArgs(e.target.value)}
                      />
                    </div>
                  </>
                )}

                <div className="connectors-hub__modal-footer">
                  <button
                    type="button"
                    className="connectors-hub__btn-secondary"
                    onClick={() => setShowAddMcpModal(false)}
                  >
                    Cancel
                  </button>
                  <button
                    type="button"
                    className="connectors-hub__primary-btn"
                    onClick={handleCreateMcp}
                  >
                    Register & Discover Tools
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* MODAL 3: CREATE CUSTOM SKILL */}
      {showAddSkillModal && (
        <div className="connectors-hub__modal-backdrop" onClick={() => setShowAddSkillModal(false)}>
          <div className="connectors-hub__modal" onClick={(e) => e.stopPropagation()}>
            <div className="connectors-hub__modal-header">
              <h3>Create Autonomous Custom Skill</h3>
              <button type="button" onClick={() => setShowAddSkillModal(false)}>
                <X size={18} />
              </button>
            </div>

            <div className="connectors-hub__modal-body">
              <div className="connectors-hub__form">
                <div className="connectors-hub__form-row">
                  <div className="connectors-hub__form-group">
                    <label>Skill Name *</label>
                    <input
                      type="text"
                      placeholder="e.g. Team Announcement Generator"
                      value={skillName}
                      onChange={(e) => setSkillName(e.target.value)}
                    />
                  </div>
                  <div className="connectors-hub__form-group">
                    <label>Skill Key (Unique Identifier) *</label>
                    <input
                      type="text"
                      placeholder="e.g. team_announcement"
                      value={skillKey}
                      onChange={(e) => setSkillKey(e.target.value)}
                    />
                  </div>
                </div>

                <div className="connectors-hub__form-group">
                  <label>Description *</label>
                  <input
                    type="text"
                    placeholder="Short description for the agent planner"
                    value={skillDesc}
                    onChange={(e) => setSkillDesc(e.target.value)}
                  />
                </div>

                <div className="connectors-hub__form-row">
                  <div className="connectors-hub__form-group">
                    <label>Execution Sandbox</label>
                    <select
                      value={skillExecType}
                      onChange={(e) => setSkillExecType(e.target.value as any)}
                    >
                      <option value="prompt">Prompt Template ({'{arg}'} placeholders)</option>
                      <option value="python_sandbox">Sandboxed Python Evaluator</option>
                    </select>
                  </div>
                  <div className="connectors-hub__form-group">
                    <label>Risk Level</label>
                    <select
                      value={skillRisk}
                      onChange={(e) => setSkillRisk(e.target.value as any)}
                    >
                      <option value="low">Low (Auto-executable)</option>
                      <option value="medium">Medium</option>
                      <option value="high">High (Guarded)</option>
                    </select>
                  </div>
                </div>

                <div className="connectors-hub__form-group">
                  <label>Template or Python Code *</label>
                  <textarea
                    rows={6}
                    value={skillTemplate}
                    onChange={(e) => setSkillTemplate(e.target.value)}
                    className="connectors-hub__code-textarea"
                  />
                </div>

                <div className="connectors-hub__form-checkbox">
                  <input
                    type="checkbox"
                    id="require_confirm"
                    checked={skillConfirm}
                    onChange={(e) => setSkillConfirm(e.target.checked)}
                  />
                  <label htmlFor="require_confirm">
                    Require explicit confirmation in Action Center before execution
                  </label>
                </div>

                <div className="connectors-hub__modal-footer">
                  <button
                    type="button"
                    className="connectors-hub__btn-secondary"
                    onClick={() => setShowAddSkillModal(false)}
                  >
                    Cancel
                  </button>
                  <button
                    type="button"
                    className="connectors-hub__primary-btn"
                    onClick={handleCreateSkill}
                  >
                    Register Skill
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* MODAL 4: TEST RUN SKILL */}
      {runningSkill && (
        <div className="connectors-hub__modal-backdrop" onClick={() => setRunningSkill(null)}>
          <div className="connectors-hub__modal" onClick={(e) => e.stopPropagation()}>
            <div className="connectors-hub__modal-header">
              <h3>Test Skill: {runningSkill.name}</h3>
              <button type="button" onClick={() => setRunningSkill(null)}>
                <X size={18} />
              </button>
            </div>

            <div className="connectors-hub__modal-body">
              <div className="connectors-hub__form">
                <div className="connectors-hub__form-group">
                  <label>Execution Arguments (JSON)</label>
                  <textarea
                    rows={4}
                    value={skillArgsInput}
                    onChange={(e) => setSkillArgsInput(e.target.value)}
                    className="connectors-hub__code-textarea"
                  />
                </div>

                <button
                  type="button"
                  className="connectors-hub__primary-btn"
                  onClick={handleRunCustomSkill}
                  disabled={skillExecuting}
                >
                  <Play size={15} />
                  <span>{skillExecuting ? 'Executing in Sandbox…' : 'Execute Skill'}</span>
                </button>

                {skillExecResult && (
                  <div className="connectors-hub__exec-output">
                    <h4>Execution Output:</h4>
                    <pre>{JSON.stringify(skillExecResult, null, 2)}</pre>
                    {onSendToChat && (
                      <button
                        type="button"
                        className="connectors-hub__action-btn"
                        style={{ marginTop: 8 }}
                        onClick={() => {
                          onSendToChat(`[Custom Skill '${runningSkill.name}'] Result:\n\`\`\`json\n${JSON.stringify(skillExecResult, null, 2)}\n\`\`\``);
                          onBack();
                        }}
                      >
                        Insert into Chat
                      </button>
                    )}
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
