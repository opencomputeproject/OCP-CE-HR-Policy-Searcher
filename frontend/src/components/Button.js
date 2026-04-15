import React from 'react';

function Button({ children, onClick, disabled, type = 'button', variant = 'primary', className = '', ...rest }) {
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      className={`button ${variant} ${className}`.trim()}
      {...rest}
    >
      {children}
    </button>
  );
}

export default Button;
