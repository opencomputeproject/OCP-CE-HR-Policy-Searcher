import React from 'react';

function ModeSelector({ value, onChange }) {
  return (
    <div className="mode-field">
      <span className="mode-label">Mode</span>
      <div className="mode-options">
        <button
          type="button"
          className={`mode-button ${value === 'discover' ? 'selected' : ''}`.trim()}
          onClick={() => onChange('discover')}
        >
          Discover
        </button>
        <button
          type="button"
          className={`mode-button ${value === 'deep' ? 'selected' : ''}`.trim()}
          onClick={() => onChange('deep')}
        >
          Deep
        </button>
        <button
          type="button"
          className={`mode-button ${value === 'interactive' ? 'selected' : ''}`.trim()}
          onClick={() => onChange('interactive')}
        >
          Interactive
        </button>
      </div>
    </div>
  );
}

export default ModeSelector;
