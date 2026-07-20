import React from 'react';

export const helpWindowStyle = {
  minHeight: 40,
  backgroundColor: '#8dc63f',
  color: '#ffffff',
};

const OCP_GREEN = '#8dc63f';
const OCP_GREEN_DARK = '#6fa52f';
const OCP_GREEN_SOFT = '#eef7e4';
const OCP_GREEN_BORDER = '#c8e5a3';

const styles = {
  backdrop: {
    position: 'fixed',
    inset: 0,
    zIndex: 1000,
    display: 'grid',
    placeItems: 'center',
    padding: 16,
    background: 'rgba(31, 41, 55, 0.46)',
  },
  modal: {
    width: 'min(100%, 560px)',
    boxSizing: 'border-box',
    padding: 20,
    borderRadius: 8,
    borderTop: `4px solid ${OCP_GREEN}`,
    background: '#ffffff',
    color: '#111827',
    boxShadow: '0 18px 60px rgba(15, 23, 42, 0.25)',
    fontFamily: '"Open Sans", "Helvetica Neue", Arial, sans-serif',
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
    fontWeight: 700,
    color: '#1f2937',
  },
  closeButton: {
    width: 32,
    height: 32,
    border: 'none',
    borderRadius: 999,
    background: '#ffffff',
    color: '#334155',
    cursor: 'pointer',
    fontSize: 18,
    fontWeight: 700,
    lineHeight: 1,
  },
  body: {
    display: 'grid',
    gap: 12,
    marginTop: 18,
  },
  intro: {
    margin: '14px 0 0',
    color: '#334155',
    fontSize: 15,
    lineHeight: 1.55,
  },
  steps: {
    display: 'grid',
    gap: 10,
    margin: '18px 0 0',
    padding: 0,
    listStyle: 'none',
  },
  step: {
    display: 'grid',
    gridTemplateColumns: '32px 1fr',
    gap: 12,
    padding: 12,
    border: `1px solid ${OCP_GREEN_BORDER}`,
    borderRadius: 8,
    background: OCP_GREEN_SOFT,
  },
  stepNumber: {
    display: 'inline-grid',
    placeItems: 'center',
    width: 28,
    height: 28,
    borderRadius: 999,
    background: OCP_GREEN,
    color: '#ffffff',
    fontWeight: 800,
    fontSize: 14,
  },
  stepTitle: {
    margin: 0,
    color: '#0f172a',
    fontSize: 15,
    fontWeight: 800,
  },
  stepText: {
    margin: '4px 0 0',
    color: '#475569',
    fontSize: 14,
    lineHeight: 1.45,
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
  adminSection: {
    marginTop: 20,
    paddingTop: 16,
    borderTop: `1px solid ${OCP_GREEN_BORDER}`,
  },
  adminHeading: {
    margin: '0 0 8px',
    color: '#1f2937',
    fontSize: 15,
    fontWeight: 800,
  },
  adminList: {
    display: 'grid',
    gap: 6,
    margin: 0,
    padding: 0,
    listStyle: 'none',
  },
  adminItem: {
    margin: 0,
    color: '#475569',
    fontSize: 14,
    lineHeight: 1.45,
  },
  keyValue: {
    display: 'inline-block',
    padding: '8px 10px',
    border: '1px solid #cbd5e1',
    borderRadius: 6,
    background: '#f8fafc',
    color: '#111827',
    fontFamily: 'inherit',
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
  primaryButton: {
    background: OCP_GREEN,
    color: '#ffffff',
  },
  primaryButtonHover: {
    background: OCP_GREEN_DARK,
  },
  footer: {
    display: 'flex',
    justifyContent: 'flex-end',
    marginTop: 18,
  },
  disabledButton: {
    background: '#999',
    cursor: 'not-allowed',
  },
};

function HelpWindow({ open, onClose, title = 'Welcome to Policy Pulse' }) {
  const [isPrimaryHovered, setIsPrimaryHovered] = React.useState(false);

  if (!open) return null;

  return (
    <div style={styles.backdrop} role="presentation">
      <div style={styles.modal} role="dialog" aria-modal="true" aria-labelledby="help-title">
        <div style={styles.header}>
          <h2 id="help-title" style={styles.title}>{title}</h2>
          
          <button type="button" style={styles.closeButton} onClick={onClose} aria-label="Close help window">
            x
          </button>
        </div>
        <p style={styles.intro}>
          Policy Pulse is free to browse for everyone - explore the map, view found policies
          for any place, and ask questions in your own language. No account or API key needed.
        </p>
        <ol style={styles.steps}>
          <li style={styles.step}>
            <span style={styles.stepNumber}>1</span>
            <div>
              <p style={styles.stepTitle}>Explore the map</p>
              <p style={styles.stepText}>
                Click a country to see its found policies. Double-click to drill into that
                country&apos;s states or provinces.
              </p>
            </div>
          </li>
          <li style={styles.step}>
            <span style={styles.stepNumber}>2</span>
            <div>
              <p style={styles.stepTitle}>View found policies</p>
              <p style={styles.stepText}>
                See the policies found for any place, and filter the list to narrow it down.
              </p>
            </div>
          </li>
          <li style={styles.step}>
            <span style={styles.stepNumber}>3</span>
            <div>
              <p style={styles.stepTitle}>Ask questions in your own language</p>
              <p style={styles.stepText}>
                Ask about what has been found, in any language. Answers come only from what
                has already been discovered.
              </p>
            </div>
          </li>
        </ol>
        <div style={styles.adminSection}>
          <p style={styles.adminHeading}>For administrators</p>
          <ul style={styles.adminList}>
            <li style={styles.adminItem}>
              Add an active Anthropic API key in API key settings before running scans or
              using the agent chat.
            </li>
            <li style={styles.adminItem}>
              Pick a scan mode: Standard for configured sources, Discover for finding new
              coverage and sources, or Deep for a more expansive and thorough crawl at a
              higher cost.
            </li>
            <li style={styles.adminItem}>
              Set budgets and daily caps to bound scan and question spend.
            </li>
            <li style={styles.adminItem}>
              Export staged results to Google Sheets for review before they go live.
            </li>
          </ul>
        </div>
        <div style={styles.footer}>
          <button
            type="button"
            style={{
              ...styles.buttonBase,
              ...styles.primaryButton,
              ...(isPrimaryHovered ? styles.primaryButtonHover : {}),
            }}
            onClick={onClose}
            onMouseEnter={() => setIsPrimaryHovered(true)}
            onMouseLeave={() => setIsPrimaryHovered(false)}
          >
            Get started
          </button>
        </div>
      </div>
    </div>
  );
}

export default HelpWindow;
