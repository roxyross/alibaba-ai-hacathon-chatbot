import React, { useEffect } from 'react';
import './Toast.css';

export interface ToastMessage {
  id: string;
  type: 'success' | 'info' | 'warning' | 'error';
  message: string;
}

interface ToastProps {
  toasts: ToastMessage[];
  onDismiss: (id: string) => void;
}

export const ToastContainer: React.FC<ToastProps> = ({ toasts, onDismiss }) => {
  return (
    <div className="toast-container" role="region" aria-live="polite" aria-label="Notifications">
      {toasts.map((toast) => (
        <ToastItem key={toast.id} toast={toast} onDismiss={() => onDismiss(toast.id)} />
      ))}
    </div>
  );
};

const ToastItem: React.FC<{ toast: ToastMessage; onDismiss: () => void }> = ({
  toast,
  onDismiss,
}) => {
  useEffect(() => {
    const timer = setTimeout(() => {
      onDismiss();
    }, 3200);
    return () => clearTimeout(timer);
  }, [onDismiss]);

  const icons = {
    success: '✓',
    info: 'ℹ',
    warning: '⚠',
    error: '✕',
  };

  return (
    <div className={`toast toast--${toast.type}`} role="alert">
      <span className="toast__icon">{icons[toast.type]}</span>
      <span className="toast__message">{toast.message}</span>
      <button
        type="button"
        className="toast__close-btn"
        onClick={onDismiss}
        aria-label="Close notification"
      >
        ✕
      </button>
    </div>
  );
};
