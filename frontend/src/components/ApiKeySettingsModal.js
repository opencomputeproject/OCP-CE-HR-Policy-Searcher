import React, { useEffect, useState } from 'react';
import { apiUrl } from '../config/api';

const styles = {
  backdrop: {
    position: 'fixed',
    inset: 0,
    zIndex: 1000,
    display: 'grid',
    placeItems: 'center',
    padding: 16,
    background: 'rgba(15, 23, 42, 0.45)',
  },
  modal: {
    width: 'min(100%, 460px)',
    boxSizing: 'border-box',
    padding: 20,
    borderRadius: 8,
    background: '#ffffff',
    color: '#111827',
    boxShadow: '0 18px 60px rgba(15, 23, 42, 0.25)',
  },
  header: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 16,
  },
  title: {
    margin: 0,
    fontSize: 20,
  },
  closeButton: {
    width: 32,
    height: 32,
    border: '1px solid #cbd5e1',
    borderRadius: 6,
    background: '#ffffff',
    color: '#111827',
    cursor: 'pointer',
    fontSize: 18,
    lineHeight: 1,
  },
  body: {
    display: 'grid',
    gap: 12,
    marginTop: 18,
  },
  label: {
    display: 'block',
    marginBottom: 6,
    color: '#334155',
    fontSize: 14,
    fontWeight: 700,
  },
  keyValue: {
    display: 'inline-block',
    padding: '8px 10px',
    border: '1px solid #cbd5e1',
    borderRadius: 6,
    background: '#f8fafc',
    color: '#111827',
    fontFamily: 'monospace',
  },
  input: {
    width: '100%',
    boxSizing: 'border-box',
    padding: '10px 12px',
    border: '1px solid #cbd5e1',
    borderRadius: 6,
    color: '#111827',
  },
  buttonBase: {
    minHeight: 40,
    padding: '10px 14px',
    border: 'none',
    borderRadius: 6,
    cursor: 'pointer',
    fontSize: 15,
    fontWeight: 700,
  },
  saveButton: {
    background: '#2563eb',
    color: '#ffffff',
  },
  dangerButton: {
    background: '#ef4444',
    color: '#ffffff',
  },
  secondaryButton: {
    background: '#e2e8f0',
    color: '#111827',
  },
  disabledButton: {
    background: '#999',
    cursor: 'not-allowed',
  },
  warning: {
    padding: 12,
    border: '1px solid #f59e0b',
    borderRadius: 6,
    background: '#fffbeb',
    color: '#92400e',
    fontSize: 14,
    lineHeight: 1.45,
  },
  actionRow: {
    display: 'flex',
    gap: 10,
    flexWrap: 'wrap',
  },
  message: {
    margin: '14px 0 0',
    color: '#334155',
    fontSize: 14,
  },
};

function buttonStyle(variant, disabled) {
  return {
    ...styles.buttonBase,
    ...(variant === 'danger' ? styles.dangerButton : {}),
    ...(variant === 'secondary' ? styles.secondaryButton : {}),
    ...(variant === 'save' ? styles.saveButton : {}),
    ...(disabled ? styles.disabledButton : {}),
  };
}

function ApiKeySettingsModal({ open, onClose }) {
  const [status, setStatus] = useState(null);
  const [apiKey, setApiKey] = useState('');
  const [message, setMessage] = useState('');
  const [isBusy, setIsBusy] = useState(false);
  const [isConfirmingDelete, setIsConfirmingDelete] = useState(false);

  const loadStatus = async () => {
    const response = await fetch(apiUrl('/api/settings/api-key'));
    if (!response.ok) {
      throw new Error('Could not load API key status.');
    }
    setStatus(await response.json());
  };

  useEffect(() => {
    if (!open) return;

    setMessage('');
    setApiKey('');
    setIsConfirmingDelete(false);
    loadStatus().catch((error) => setMessage(error.message));
  }, [open]);

  const saveKey = async () => {
    setIsBusy(true);
    setMessage('');

    try {
      const response = await fetch(apiUrl('/api/settings/api-key'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ api_key: apiKey }),
      });

      if (!response.ok) {
        const error = await response.json().catch(() => ({}));
        throw new Error(error.detail || 'Could not save API key.');
      }

      const nextStatus = await response.json();
      setStatus(nextStatus);
      setApiKey('');
      setMessage('API key saved.');
    } catch (error) {
      setMessage(error.message);
    } finally {
      setIsBusy(false);
    }
  };

  const deleteKey = async () => {
    setIsBusy(true);
    setMessage('');

    try {
      const response = await fetch(apiUrl('/api/settings/api-key'), {
        method: 'DELETE',
      });

      if (!response.ok) {
        throw new Error('Could not delete API key.');
      }

      setStatus(await response.json());
      setMessage('API key deleted.');
      setIsConfirmingDelete(false);
    } catch (error) {
      setMessage(error.message);
    } finally {
      setIsBusy(false);
    }
  };

  if (!open) return null;

  const saveDisabled = isBusy || !apiKey.trim();

  return (
    <div style={styles.backdrop} role="presentation">
      <div style={styles.modal} role="dialog" aria-modal="true" aria-labelledby="api-key-title">
        <div style={styles.header}>
          <h2 id="api-key-title" style={styles.title}>API key settings</h2>
          
          <button type="button" style={styles.closeButton} onClick={onClose} aria-label="Close settings">
            x
          </button>
        </div>
        <div style={styles.label}>
              An Anthropic API key is needed for the Policy Pulse agent to function.
        </div>

        {status?.exists ? (
          <div style={styles.body}>
            <div>
              <span style={styles.label}>Current key</span>
              <span style={styles.keyValue}>{status.masked}</span>
            </div>
            {isConfirmingDelete ? (
              <>
                <div style={styles.warning}>
                  Deleting this key will disable agent and LLM features until a new Anthropic API key is saved.
                </div>
                <div style={styles.actionRow}>
                  <button
                    type="button"
                    style={buttonStyle('danger', isBusy)}
                    onClick={deleteKey}
                    disabled={isBusy}
                  >
                    Confirm delete
                  </button>
                  <button
                    type="button"
                    style={buttonStyle('secondary', isBusy)}
                    onClick={() => setIsConfirmingDelete(false)}
                    disabled={isBusy}
                  >
                    Cancel
                  </button>
                </div>
              </>
            ) : (
              <button
                type="button"
                style={buttonStyle('danger', isBusy)}
                onClick={() => {
                  setMessage('');
                  setIsConfirmingDelete(true);
                }}
                disabled={isBusy}
              >
                Delete key
              </button>
            )}
          </div>
        ) : (
          <div style={styles.body}>
            <label style={styles.label} htmlFor="api-key-input">
              Anthropic API key
            </label>
            <input
              id="api-key-input"
              type="password"
              value={apiKey}
              onChange={(event) => setApiKey(event.target.value)}
              placeholder="sk-ant-..."
              autoComplete="off"
              style={styles.input}
            />
            <button
              type="button"
              style={buttonStyle('save', saveDisabled)}
              onClick={saveKey}
              disabled={saveDisabled}
            >
              Add an API key
            </button>
          </div>
        )}

        {message ? <p style={styles.message}>{message}</p> : null}
      </div>
    </div>
  );
}

export default ApiKeySettingsModal;
