import React, { useMemo } from 'react';
import { useModels } from './useModels';
import './ModelPicker.css';

export interface ModelSelection {
  provider: string;
  model: string;
}

interface ModelPickerProps {
  value: ModelSelection | null;
  onChange: (next: ModelSelection) => void;
}

export const ModelPicker: React.FC<ModelPickerProps> = ({ value, onChange }) => {
  const { providers, loading, error } = useModels();

  const grouped = useMemo(() => {
    return providers.filter((p) => p.enabled);
  }, [providers]);

  return (
    <div className="model-picker">
      <label className="model-picker__label" htmlFor="model-picker-select">
        Model
      </label>
      <select
        id="model-picker-select"
        className="model-picker__select"
        value={value ? `${value.provider}/${value.model}` : ''}
        onChange={(e) => {
          const [provider, ...rest] = e.target.value.split('/');
          if (!provider) return;
          onChange({ provider, model: rest.join('/') });
        }}
        disabled={loading || !!error}
      >
        <option value="" disabled>
          {loading
            ? 'Loading models…'
            : error
              ? 'Failed to load models'
              : 'Select a model'}
        </option>
        <optgroup label="Runtime">
          <option value="runtime/">Runtime Coordinator</option>
        </optgroup>
        {grouped.map((p) => (
          <optgroup key={p.name} label={p.display_name || p.name}>
            {p.models
              .filter((m) => m.enabled)
              .map((m) => (
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
      {error && <p className="model-picker__error">{error}</p>}
    </div>
  );
};
