import { Component, ErrorInfo, ReactNode } from 'react';
import { AlertCircle, RefreshCw, ArrowLeft } from 'lucide-react';

interface Props {
  children: ReactNode;
  onBack?: () => void;
  onRetry?: () => void;
  savedQuery?: string;
}

interface State {
  hasError: boolean;
  errorMessage: string;
}

export class ResearchErrorBoundary extends Component<Props, State> {
  public state: State = {
    hasError: false,
    errorMessage: '',
  };

  public static getDerivedStateFromError(error: Error): State {
    return {
      hasError: true,
      errorMessage: error?.message || 'An unexpected rendering error occurred during research synthesis.',
    };
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
    // Log technical diagnostics safely to console for debugging without leaking secrets
    console.error('ResearchErrorBoundary caught an exception:', error, errorInfo);
  }

  private handleReset = (): void => {
    this.setState({ hasError: false, errorMessage: '' });
    if (this.props.onRetry) {
      this.props.onRetry();
    }
  };

  public render(): ReactNode {
    if (this.state.hasError) {
      return (
        <div className="research-hub" style={{ minHeight: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '2rem' }}>
          <div
            style={{
              maxWidth: '560px',
              width: '100%',
              background: '#ffffff',
              border: '1px solid #e2e8e6',
              borderRadius: '16px',
              padding: '2rem',
              boxShadow: '0 10px 25px -5px rgba(0, 0, 0, 0.05), 0 8px 10px -6px rgba(0, 0, 0, 0.02)',
              textAlign: 'center',
            }}
          >
            <div
              style={{
                width: '48px',
                height: '48px',
                borderRadius: '12px',
                background: 'rgba(239, 68, 68, 0.1)',
                color: '#ef4444',
                display: 'inline-flex',
                alignItems: 'center',
                justifyContent: 'center',
                marginBottom: '1rem',
              }}
            >
              <AlertCircle size={26} />
            </div>

            <h2 style={{ fontSize: '1.25rem', fontWeight: 700, color: '#1e292b', marginBottom: '0.5rem' }}>
              Research couldn't be completed
            </h2>

            <p style={{ fontSize: '0.875rem', color: '#64748b', lineHeight: 1.5, marginBottom: '1.25rem' }}>
              A rendering issue was encountered while processing this research report. Your query and session remain safe.
            </p>

            {this.props.savedQuery && (
              <div
                style={{
                  background: '#f8fafc',
                  border: '1px solid #e2e8f0',
                  borderRadius: '8px',
                  padding: '0.75rem 1rem',
                  fontSize: '0.8125rem',
                  color: '#334155',
                  marginBottom: '1.5rem',
                  textAlign: 'left',
                }}
              >
                <span style={{ fontWeight: 600, color: '#0d9488' }}>Preserved Query: </span>
                <span>{this.props.savedQuery}</span>
              </div>
            )}

            <div style={{ display: 'flex', gap: '0.75rem', justifyContent: 'center' }}>
              {this.props.onBack && (
                <button
                  type="button"
                  onClick={this.props.onBack}
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '0.4rem',
                    padding: '0.6rem 1.1rem',
                    borderRadius: '8px',
                    border: '1px solid #cbd5e1',
                    background: '#ffffff',
                    color: '#475569',
                    fontSize: '0.875rem',
                    fontWeight: 600,
                    cursor: 'pointer',
                  }}
                >
                  <ArrowLeft size={16} />
                  <span>Back</span>
                </button>
              )}

              <button
                type="button"
                onClick={this.handleReset}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '0.4rem',
                  padding: '0.6rem 1.25rem',
                  borderRadius: '8px',
                  border: 'none',
                  background: '#0d9488',
                  color: '#ffffff',
                  fontSize: '0.875rem',
                  fontWeight: 600,
                  cursor: 'pointer',
                  boxShadow: '0 2px 4px rgba(13, 148, 136, 0.2)',
                }}
              >
                <RefreshCw size={16} />
                <span>Retry</span>
              </button>
            </div>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
