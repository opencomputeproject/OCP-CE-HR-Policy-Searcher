import React from 'react';

function MessageItem({ type, children }) {
  const label = type === 'user'
    ? 'You:'
    : type === 'agent'
    ? 'CLI Agent:'
    : type === 'error'
    ? 'Error:'
    : 'System:';

  return (
    <div className={`message-item ${type}`}>
      <strong>{label}</strong>{' '}
      {children}
    </div>
  );
}

export default MessageItem;
