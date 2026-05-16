import React, { useEffect, useState } from 'react';

const API_BASE_URL = process.env.REACT_APP_API_BASE_URL || 'http://127.0.0.1:8000';

export const helpWindowStyle = {
  minHeight: 40,
  backgroundColor: '#bccdf4',
  color: '#000000',
};

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
  freetext: {
    display: 'block',
    marginBottom: 6,
    fontSize: 14,
    color: '#0f172a'
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
  buttonBase: {
    minHeight: 40,
    padding: '10px 14px',
    border: 'none',
    borderRadius: 6,
    cursor: 'pointer',
    fontSize: 15,
    fontWeight: 700,
  },
  secondaryButton: {
    background: '#e2e8f0',
    color: '#111827',
  },
  disabledButton: {
    background: '#999',
    cursor: 'not-allowed',
  },
};

function HelpWindow({ open, onClose }) {
  const [status, setStatus] = useState(null);
  const [message, setMessage] = useState('');


  useEffect(() => {
    if (!open) return;

    setMessage('');
  }, [open]);

  if (!open) return null;

  return (
    <div style={styles.backdrop} role="presentation">
      <div style={styles.modal} role="dialog" aria-modal="true" aria-labelledby="help-title">
        <div style={styles.header}>
          <h2 id="help-title" style={styles.title}>Help window</h2>
          
          <button type="button" style={styles.closeButton} onClick={onClose} aria-label="Close help window">
            x
          </button>
        </div>
        <div style={styles.label}>Welcome to the PolicyPulse!</div>
        <div style={styles.freetext}>
              This is an AI based tool that helps you to find policies and regulations regarding the heat usage of datacenters.<br></br><br></br>
              You can either use the predefined search modes of the Policy Scanner, or ask the AI directly by typing your question in the chat.<br></br><br></br>
              Please note that you need an active Anthropic API key for the tool to work.   
        </div>
      </div>
    </div>
  );
}

export default HelpWindow;
