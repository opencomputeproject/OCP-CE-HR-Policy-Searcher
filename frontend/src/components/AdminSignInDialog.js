import React, { useEffect, useState } from 'react';
import { getAdminToken, setAdminToken } from '../utils/adminAuth';

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
    width: 'min(100%, 420px)',
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
  actionRow: {
    display: 'flex',
    gap: 10,
    flexWrap: 'wrap',
  },
  message: {
    margin: 0,
    color: '#334155',
    fontSize: 14,
    lineHeight: 1.45,
  },
};

function buttonStyle(variant) {
  return {
    ...styles.buttonBase,
    ...(variant === 'danger' ? styles.dangerButton : {}),
    ...(variant === 'secondary' ? styles.secondaryButton : {}),
    ...(variant === 'save' ? styles.saveButton : {}),
  };
}

function AdminSignInDialog({ open, onClose, onAdminTokenChange }) {
  const [tokenValue, setTokenValue] = useState('');
  const [hasStoredToken, setHasStoredToken] = useState(false);

  useEffect(() => {
    if (!open) return;

    const stored = getAdminToken();
    setTokenValue(stored);
    setHasStoredToken(Boolean(stored));
  }, [open]);

  if (!open) return null;

  const handleSave = () => {
    setAdminToken(tokenValue);
    onAdminTokenChange?.();
    onClose();
  };

  const handleSignOut = () => {
    setAdminToken('');
    onAdminTokenChange?.();
    setTokenValue('');
    setHasStoredToken(false);
  };

  return (
    <div style={styles.backdrop} role="presentation">
      <div style={styles.modal} role="dialog" aria-modal="true" aria-labelledby="admin-sign-in-title">
        <div style={styles.header}>
          <h2 id="admin-sign-in-title" style={styles.title}>Admin sign-in</h2>
          <button
            type="button"
            style={styles.closeButton}
            onClick={onClose}
            aria-label="Close admin sign-in"
          >
            &times;
          </button>
        </div>
        <div style={styles.body}>
          <label style={styles.label} htmlFor="admin-passphrase-input">
            Admin passphrase
          </label>
          <input
            id="admin-passphrase-input"
            type="password"
            value={tokenValue}
            onChange={(event) => setTokenValue(event.target.value)}
            placeholder="Admin passphrase"
            autoComplete="off"
            style={styles.input}
          />
          <p style={styles.message}>
            Set by the server operator via the ADMIN_TOKEN environment variable - unlocks
            scanning and review tools.
          </p>
          <div style={styles.actionRow}>
            <button type="button" style={buttonStyle('save')} onClick={handleSave}>
              Save
            </button>
            <button type="button" style={buttonStyle('secondary')} onClick={onClose}>
              Cancel
            </button>
          </div>
          {hasStoredToken && (
            <button type="button" style={buttonStyle('danger')} onClick={handleSignOut}>
              Sign out
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

export default AdminSignInDialog;
