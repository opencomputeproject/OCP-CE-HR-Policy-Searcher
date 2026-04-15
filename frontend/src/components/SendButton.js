import React from 'react';
import Button from './Button';

function SendButton({ isLoading, onClick, disabled }) {
  return (
    <Button
      onClick={onClick}
      disabled={disabled}
      variant="secondary"
      className="send-button"
    >
      {isLoading ? 'Running CLI Agent...' : 'Send to CLI Agent'}
    </Button>
  );
}

export default SendButton;
