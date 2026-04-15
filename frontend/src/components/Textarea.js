import React from 'react';

function Textarea({ value, onChange, onKeyPress, placeholder, disabled, className = '', ...rest }) {
  return (
    <textarea
      value={value}
      onChange={onChange}
      onKeyPress={onKeyPress}
      placeholder={placeholder}
      disabled={disabled}
      className={`textarea ${className}`.trim()}
      {...rest}
    />
  );
}

export default Textarea;
