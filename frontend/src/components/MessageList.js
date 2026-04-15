import React from 'react';
import MessageItem from './MessageItem';

function MessageList({ messages, scrollRef }) {
  return (
    <div className="message-panel">
      {messages.map((msg, index) => (
        <MessageItem key={index} type={msg.type}>
          {msg.content}
        </MessageItem>
      ))}
      <div ref={scrollRef} />
    </div>
  );
}

export default MessageList;
