import React from 'react';
import Button from './Button';

function ConnectButton({ connected, onClick, disabled }) {
  return (
    <Button
      onClick={onClick}
      disabled={disabled}
      variant="primary"
      className="connect-button"
    >
      {connected ? 'Connected' : 'Connect to CLI Agent'}
    </Button>
  );
}

export default ConnectButton;
