'use client';
import * as React from 'react';
import Box from '@mui/material/Box';
import {
  ChatComposer,
  ChatComposerSendButton,
  ChatComposerTextArea,
  ChatComposerToolbar,
} from '@mui/x-chat/ChatComposer';
import { ChatConversation } from '@mui/x-chat/ChatConversation';
import { ChatMessageList } from '@mui/x-chat/ChatMessageList';
import {
  ChatMessage,
  ChatMessageAvatar,
  ChatMessageContent,
  ChatMessageGroup,
} from '@mui/x-chat/ChatMessage';
import { ChatProvider, useChat, useChatStore, useMessageIds } from '@mui/x-chat/headless';

const CONVERSATION_ID = 'cli-agent-conv';

const chatUsers = {
  agent: {
    id: 'cli-agent',
    displayName: 'CLI Agent',
    role: 'assistant',
  },
  you: {
    id: 'you',
    displayName: 'You',
    role: 'user',
  },
  system: {
    id: 'system',
    displayName: 'System',
    role: 'system',
  },
};

const initialConversations = [
  {
    id: CONVERSATION_ID,
    title: 'CLI Agent',
    subtitle: 'Connected to the policy search agent',
    participants: [chatUsers.agent, chatUsers.you],
  },
];

const initialMessages = [
  createTextMessage({
    id: 'system-welcome',
    conversationId: CONVERSATION_ID,
    role: 'system',
    author: chatUsers.system,
    createdAt: new Date().toISOString(),
    text: 'Connect to the CLI agent, then send a command or run a scan.',
  }),
];

function SendIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="currentColor"
      aria-hidden="true"
      style={{ width: '1em', height: '1em' }}
    >
      <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z" />
    </svg>
  );
}

function createTextMessage({ text, ...message }) {
  return {
    ...message,
    parts: [{ type: 'text', text, state: 'done' }],
    status: 'sent',
  };
}

function getMessageText(message) {
  return message.parts
    ?.filter((part) => part.type === 'text')
    .map((part) => part.text)
    .join('') ?? '';
}

function enqueueTextResponse(controller, messageId, text) {
  controller.enqueue({ type: 'start', messageId });
  controller.enqueue({ type: 'text-start', id: `${messageId}-text` });
  controller.enqueue({ type: 'text-delta', id: `${messageId}-text`, delta: text });
  controller.enqueue({ type: 'text-end', id: `${messageId}-text` });
  controller.enqueue({ type: 'finish', messageId });
  controller.close();
}

function createWebSocketResponseStream({ ws, text, signal, onRunningChange }) {
  return new ReadableStream({
    start(controller) {
      const messageId = `response-${Date.now()}`;
      const textId = `${messageId}-text`;
      let settled = false;

      const cleanup = () => {
        ws.removeEventListener('message', handleMessage);
        ws.removeEventListener('error', handleError);
        ws.removeEventListener('close', handleClose);
        signal?.removeEventListener('abort', handleAbort);
        onRunningChange?.(false);
      };

      const startMessage = () => {
        controller.enqueue({ type: 'start', messageId });
        controller.enqueue({ type: 'text-start', id: textId });
      };

      const enqueueDelta = (delta) => {
        if (settled) return;
        controller.enqueue({ type: 'text-delta', id: textId, delta });
      };

      const settleFinish = () => {
        if (settled) return;
        settled = true;
        cleanup();
        controller.enqueue({ type: 'text-end', id: textId });
        controller.enqueue({ type: 'finish', messageId });
        controller.close();
      };

      const settleWithError = (responseText) => {
        if (settled) return;
        settled = true;
        cleanup();
        controller.enqueue({ type: 'text-delta', id: textId, delta: responseText });
        controller.enqueue({ type: 'text-end', id: textId });
        controller.enqueue({ type: 'finish', messageId });
        controller.close();
      };

      const handleMessage = (event) => {
        if (settled) return;

        let payload;
        try {
          payload = JSON.parse(event.data);
        } catch {
          enqueueDelta(event.data);
          return;
        }

        switch (payload.type) {
          case 'text':
            enqueueDelta(payload.content || '');
            break;
          case 'tool_call':
            enqueueDelta(`\n[tool_call ${payload.name}] ${JSON.stringify(payload.input)}\n`);
            break;
          case 'tool_result':
            enqueueDelta(`\n[tool_result ${payload.name}] ${JSON.stringify(payload.result)}\n`);
            break;
          case 'complete':
            if (payload.response) {
              enqueueDelta(payload.response);
            }
            settleFinish();
            break;
          case 'error':
            settleWithError(payload.content || 'Agent error');
            break;
          default:
            enqueueDelta(event.data);
        }
      };

      const handleError = () => {
        settleWithError('Connection error');
      };

      const handleClose = () => {
        settleWithError('Disconnected from policy agent');
      };

      const handleAbort = () => {
        if (settled) return;
        settled = true;
        cleanup();
        controller.enqueue({ type: 'abort', messageId });
        controller.close();
      };

      ws.addEventListener('message', handleMessage);
      ws.addEventListener('error', handleError);
      ws.addEventListener('close', handleClose);
      signal?.addEventListener('abort', handleAbort);

      onRunningChange?.(true);
      startMessage();
      ws.send(JSON.stringify({ message: text }));
    },
  });
}

function createCliAgentAdapter({ wsRef, onRunningChange }) {
  return {
    async sendMessage({ message, signal }) {
      const text = getMessageText(message).trim();
      const ws = wsRef.current;

      if (!ws || ws.readyState !== WebSocket.OPEN) {
        return new ReadableStream({
          start(controller) {
            enqueueTextResponse(
              controller,
              `response-${Date.now()}`,
              'Connect to the CLI agent before sending a command.',
            );
          },
        });
      }

      if (!text) {
        return new ReadableStream({
          start(controller) {
            enqueueTextResponse(controller, `response-${Date.now()}`, 'Enter a command first.');
          },
        });
      }

      return createWebSocketResponseStream({ ws, text, signal, onRunningChange });
    },
  };
}

const ChatbotInner = React.forwardRef(function ChatbotInner(
  { disabled, notice, onRunningChange },
  ref,
) {
  const { sendMessage, isStreaming } = useChat();
  const chatStore = useChatStore();
  const messageIds = useMessageIds();
  const inputDisabled = disabled || isStreaming;
  const handledNoticeIdRef = React.useRef(null);

  React.useImperativeHandle(
    ref,
    () => ({
      sendCommand(command) {
        const text = command.trim();
        if (!text || inputDisabled) return;

        sendMessage({
          conversationId: CONVERSATION_ID,
          author: chatUsers.you,
          parts: [{ type: 'text', text }],
        });
      },
    }),
    [inputDisabled, sendMessage],
  );

  React.useEffect(() => {
    onRunningChange?.(isStreaming);
  }, [isStreaming, onRunningChange]);

  React.useEffect(() => {
    if (!notice || handledNoticeIdRef.current === notice.id) return;

    handledNoticeIdRef.current = notice.id;

    chatStore.addMessage(createTextMessage({
      id: `${notice.type}-${notice.id}`,
      conversationId: CONVERSATION_ID,
      role: notice.type === 'error' ? 'assistant' : 'system',
      author: notice.type === 'error' ? chatUsers.agent : chatUsers.system,
      createdAt: new Date().toISOString(),
      text: notice.text,
    }));
  }, [chatStore, notice]);

  const renderItem = React.useCallback(
    (params) => (
      <ChatMessageGroup key={params.id} messageId={params.id}>
        <ChatMessage messageId={params.id}>
          <ChatMessageAvatar />
          <ChatMessageContent />
        </ChatMessage>
      </ChatMessageGroup>
    ),
    [],
  );

  return (
    <ChatConversation>
      <ChatMessageList renderItem={renderItem} items={messageIds} />
      <ChatComposer disabled={inputDisabled}>
        <ChatComposerTextArea
          placeholder={
            disabled
              ? 'Connect to the CLI agent before sending commands...'
              : 'Type your command here...'
          }
          disabled={inputDisabled}
        />
        <ChatComposerToolbar>
          <ChatComposerSendButton aria-label="Send message" disabled={inputDisabled}>
            <SendIcon />
          </ChatComposerSendButton>
        </ChatComposerToolbar>
      </ChatComposer>
    </ChatConversation>
  );
});

const Chatbot = React.forwardRef(function Chatbot(
  { wsRef, isConnected, notice, onRunningChange },
  ref,
) {
  const adapter = React.useMemo(
    () => createCliAgentAdapter({ wsRef, onRunningChange }),
    [wsRef, onRunningChange],
  );

  return (
    <ChatProvider
      adapter={adapter}
      initialActiveConversationId={CONVERSATION_ID}
      initialConversations={initialConversations}
      initialMessages={initialMessages}
      members={[chatUsers.agent, chatUsers.you, chatUsers.system]}
      currentUser={chatUsers.you}
    >
      <Box
        sx={{
          display: 'flex',
          flexDirection: 'column',
          height: 500,
          border: '1px solid',
          borderColor: 'divider',
          borderRadius: 1,
          overflow: 'hidden',
          boxSizing: 'border-box',
          '*, *::before, *::after': { boxSizing: 'inherit' },
        }}
      >
        <ChatbotInner
          ref={ref}
          disabled={!isConnected}
          notice={notice}
          onRunningChange={onRunningChange}
        />
      </Box>
    </ChatProvider>
  );
});

export default Chatbot;
