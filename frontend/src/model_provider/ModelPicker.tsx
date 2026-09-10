import React, { useEffect, useMemo } from 'react';
import { useModels, type ProviderModels, type ModelInfo } from './useModels';
import './ModelPicker.css';

export interface ModelSelection {
  provider: string;
  model: string;
}

interface ModelPickerProps {
  value: ModelSelection | null;
  onChange: (next: ModelSelection) => void;
}

const DEFAULT_PROVIDERS: ProviderModels[] = [
  {
    name: 'gemini',
    display_name: 'Google Gemini',
    enabled: true,
    models: [
      {
        name: 'gemini-3.6-flash',
        display_name: 'Gemini 3.6 Flash (Fast & Comprehensive)',
        enabled: true,
        task_types: ['general', 'coding', 'reasoning'],
        max_tokens: 16384,
      },
      {
        name: 'gemini-3.8-flash',
        display_name: 'Gemini 3.8 Flash (Multimodal Audio Flagship)',
        enabled: true,
        task_types: ['general', 'coding', 'reasoning'],
        max_tokens: 16384,
      },
      {
        name: 'gemini-3.7-flash',
        display_name: 'Gemini 3.7 Flash (Fast Multimodal Voice)',
        enabled: true,
        task_types: ['general', 'coding'],
        max_tokens: 16384,
      },
      {
        name: 'gemini-3.1-flash',
        display_name: 'Gemini 3.1 Flash (Steerable Voice & TTS)',
        enabled: true,
        task_types: ['general', 'coding'],
        max_tokens: 16384,
      },
      {
        name: 'gemini-2.5-flash',
        display_name: 'Gemini 2.5 Flash',
        enabled: true,
        task_types: ['general', 'coding'],
        max_tokens: 8192,
      },
      {
        name: 'gemini-2.0-flash',
        display_name: 'Gemini 2.0 Flash',
        enabled: true,
        task_types: ['general', 'coding'],
        max_tokens: 8192,
      },
      {
        name: 'gemini-1.5-pro',
        display_name: 'Gemini 1.5 Pro (Deep Reasoning)',
        enabled: true,
        task_types: ['general', 'coding'],
        max_tokens: 8192,
      },
      {
        name: 'gemini-1.5-flash',
        display_name: 'Gemini 1.5 Flash (Ultra Fast)',
        enabled: true,
        task_types: ['general'],
        max_tokens: 8192,
      },
    ],
  },
  {
    name: 'grok',
    display_name: 'xAI / Groq',
    enabled: true,
    models: [
      {
        name: 'qwen/qwen3.8-27b',
        display_name: 'Groq / Qwen 27B (High Speed & Full Responses)',
        enabled: true,
        task_types: ['general', 'coding', 'reasoning'],
        max_tokens: 4096,
      },
      {
        name: 'openai/gpt-oss-120b',
        display_name: 'Groq / GPT-OSS 120B (Deep Reasoning)',
        enabled: true,
        task_types: ['general', 'coding', 'reasoning'],
        max_tokens: 4096,
      },
      {
        name: 'qwen/qwen3.6-27b',
        display_name: 'Groq / Qwen 3.6 27B',
        enabled: true,
        task_types: ['general', 'coding'],
        max_tokens: 4096,
      },
      {
        name: 'grok-3',
        display_name: 'xAI Grok 3 (Flagship)',
        enabled: true,
        task_types: ['general', 'coding', 'reasoning'],
        max_tokens: 8192,
      },
      {
        name: 'grok-3-mini',
        display_name: 'xAI Grok 3 Mini (Fast Reasoning)',
        enabled: true,
        task_types: ['general', 'coding', 'reasoning'],
        max_tokens: 8192,
      },
      {
        name: 'grok-2',
        display_name: 'xAI Grok 2',
        enabled: true,
        task_types: ['general', 'coding'],
        max_tokens: 8192,
      },
      {
        name: 'grok-2-vision-1212',
        display_name: 'xAI Grok 2 Vision',
        enabled: true,
        task_types: ['general'],
        max_tokens: 8192,
      },
      {
        name: 'grok-beta',
        display_name: 'xAI Grok Beta',
        enabled: true,
        task_types: ['general'],
        max_tokens: 8192,
      },
      {
        name: 'llama-3.3-70b-versatile',
        display_name: 'Groq Llama 3.3 70B',
        enabled: true,
        task_types: ['general', 'coding'],
        max_tokens: 4096,
      },
      {
        name: 'mixtral-8x7b-32768',
        display_name: 'Groq Mixtral 8x7B (Ultra Fast)',
        enabled: true,
        task_types: ['general'],
        max_tokens: 4096,
      },
    ],
  },
  {
    name: 'openai',
    display_name: 'OpenAI',
    enabled: true,
    models: [
      {
        name: 'gpt-4o',
        display_name: 'GPT-4o',
        enabled: true,
        task_types: ['general', 'coding'],
        max_tokens: 4096,
      },
      {
        name: 'gpt-4o-mini',
        display_name: 'GPT-4o Mini',
        enabled: true,
        task_types: ['general', 'coding'],
        max_tokens: 4096,
      },
    ],
  },
  {
    name: 'deepseek',
    display_name: 'DeepSeek',
    enabled: true,
    models: [
      {
        name: 'deepseek-chat',
        display_name: 'DeepSeek V3',
        enabled: true,
        task_types: ['general', 'coding'],
        max_tokens: 4096,
      },
      {
        name: 'deepseek-reasoner',
        display_name: 'DeepSeek R1',
        enabled: true,
        task_types: ['reasoning'],
        max_tokens: 4096,
      },
    ],
  },
];

export const ModelPicker: React.FC<ModelPickerProps> = ({ value, onChange }) => {
  const { providers } = useModels();

  const grouped = useMemo(() => {
    const list = providers.length > 0 ? providers : DEFAULT_PROVIDERS;
    // Strictly filter out runtime/coordinator
    return list
      .filter((p) => p.enabled && p.name !== 'runtime')
      .map((p) => ({
        ...p,
        models: p.models.filter((m) => m.name !== 'coordinator'),
      }))
      .filter((p) => p.models.length > 0);
  }, [providers]);

  // If currently selected is runtime, migrate to gemini-2.0-flash
  useEffect(() => {
    if (!value || value.provider === 'runtime' || value.model === 'coordinator') {
      onChange({ provider: 'gemini', model: 'gemini-2.0-flash' });
    }
  }, [value, onChange]);

  const currentValue =
    value && value.provider !== 'runtime'
      ? `${value.provider}/${value.model}`
      : 'gemini/gemini-2.0-flash';

  return (
    <div className="model-picker">
      <label className="model-picker__label" htmlFor="model-picker-select">
        Model
      </label>
      <select
        id="model-picker-select"
        className="model-picker__select"
        value={currentValue}
        onChange={(e) => {
          const [provider, ...rest] = e.target.value.split('/');
          if (!provider) return;
          onChange({ provider, model: rest.join('/') });
        }}
      >
        {grouped.map((p) => (
          <optgroup key={p.name} label={p.display_name || p.name}>
            {p.models
              .filter((m: ModelInfo) => m.enabled)
              .map((m: ModelInfo) => (
                <option
                  key={`${p.name}/${m.name}`}
                  value={`${p.name}/${m.name}`}
                >
                  {m.display_name || m.name}
                </option>
              ))}
          </optgroup>
        ))}
      </select>
    </div>
  );
};
