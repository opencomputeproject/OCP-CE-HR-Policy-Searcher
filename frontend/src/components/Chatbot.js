'use client';
import * as React from 'react';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Paper from '@mui/material/Paper';
import Typography from '@mui/material/Typography';
import { styled } from '@mui/material/styles';
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
  ChatMessageContent,
  ChatMessageGroup,
} from '@mui/x-chat/ChatMessage';
import { ChatProvider, useChat, useChatStore, useMessageIds } from '@mui/x-chat/headless';

const CONVERSATION_ID = 'cli-agent-conv';

const chatUsers = {
  agent: {
    id: 'cli-agent',
    displayName: 'Policy Agent',
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
    title: 'Policy Agent',
    subtitle: 'Connected to the policy search agent',
    participants: [chatUsers.agent, chatUsers.you],
  },
];

const initialMessages = [];

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

function getToolStatusText(toolName) {
  const labels = {
    list_domains: 'Checking configured domains...',
    estimate_cost: 'Estimating scan cost...',
    start_scan: 'Starting scan...',
    get_scan_status: 'Checking scan progress...',
    list_scans: 'Checking recent scans...',
    search_policies: 'Searching saved policies...',
    get_policy_stats: 'Checking policy statistics...',
    get_audit_advisory: 'Checking audit advisory...',
    analyze_url: 'Analyzing webpage...',
    add_domain: 'Adding domain...',
    stop_scan: 'Stopping scan...',
  };

  return labels[toolName] || `Using ${toolName}...`;
}

// --- Custom Part Renderers for Agentic Features ---

const ReasoningBlock = styled(Paper)(({ theme }) => ({
  backgroundColor: theme.palette.grey[50],
  border: `1px solid ${theme.palette.grey[200]}`,
  borderRadius: theme.shape.borderRadius,
  padding: theme.spacing(1.5),
  margin: theme.spacing(1, 0),
  fontStyle: 'italic',
  color: theme.palette.text.secondary,
}));

const ToolBlock = styled(Paper)(({ theme }) => ({
  backgroundColor: theme.palette.blue[50],
  border: `1px solid ${theme.palette.blue[200]}`,
  borderRadius: theme.shape.borderRadius,
  padding: theme.spacing(1.5),
  margin: theme.spacing(1, 0),
  fontFamily: 'monospace',
  fontSize: '0.875rem',
}));

function ReasoningPart({ part }) {
  return (
    <ReasoningBlock>
      <Typography variant="body2" component="div">
        Reasoning: {part.text}
      </Typography>
    </ReasoningBlock>
  );
}

const messageSx = {
  gridTemplateColumns: '1fr',
  gridTemplateAreas: '"content" "actions"',
  paddingInline: 2,
  paddingBlock: '0 16px',
  '& .MuiChatMessage-content': {
    width: '100%',
  },
  '& .MuiChatMessage-bubble': {
    width: '100%',
    padding: 0,
    borderRadius: 0,
    backgroundColor: 'transparent',
    color: 'text.primary',
    fontSize: '0.95rem',
    lineHeight: 1.65,
  },
  '& .MuiChatMessage-bubble p': {
    marginBottom: 1,
  },
  '& .MuiChatMessage-bubble p:last-child': {
    marginBottom: 0,
  },
  '&.MuiChatMessage-roleUser .MuiChatMessage-content': {
    alignItems: 'flex-end',
  },
  '&.MuiChatMessage-roleUser .MuiChatMessage-bubble': {
    width: 'fit-content',
    maxWidth: 'min(78%, 680px)',
    padding: '10px 14px',
    borderRadius: '16px',
    borderTopRightRadius: 4,
    backgroundColor: 'primary.main',
    color: 'primary.contrastText',
    lineHeight: 1.45,
    whiteSpace: 'pre-wrap',
  },
  '&.MuiChatMessage-roleAssistant .MuiChatMessage-content': {
    alignItems: 'stretch',
  },
  '&.MuiChatMessage-roleAssistant .MuiChatMessage-bubble': {
    maxWidth: '100%',
  },
};

function ToolPart({ part, onApprove, onDeny }) {
  const { toolInvocation } = part;
  const { toolName, input, output, state } = toolInvocation;

  return (
    <ToolBlock>
      <Typography variant="subtitle2" gutterBottom>
        Tool: {toolName}
      </Typography>
      <Typography variant="body2" component="pre" sx={{ whiteSpace: 'pre-wrap' }}>
        Input: {JSON.stringify(input, null, 2)}
      </Typography>
      {output && (
        <Typography variant="body2" component="pre" sx={{ whiteSpace: 'pre-wrap', marginTop: 1 }}>
          Output: {JSON.stringify(output, null, 2)}
        </Typography>
      )}
      {state === 'approval-requested' && (
        <Box sx={{ marginTop: 1 }}>
          <Button
            size="small"
            variant="contained"
            color="success"
            onClick={() => onApprove?.(toolInvocation.toolCallId)}
            sx={{ marginRight: 1 }}
          >
            Approve
          </Button>
          <Button
            size="small"
            variant="outlined"
            color="error"
            onClick={() => onDeny?.(toolInvocation.toolCallId)}
          >
            Deny
          </Button>
        </Box>
      )}
    </ToolBlock>
  );
}

// --- Scripted chunk builder for new messages ---------------------------------

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
      let settled = false;
      let messageCount = 0;
      let lastMessageId = null;

      const nextMessageId = () => `response-${Date.now()}-${messageCount++}`;

      const cleanup = () => {
        ws.removeEventListener('message', handleMessage);
        ws.removeEventListener('error', handleError);
        ws.removeEventListener('close', handleClose);
        signal?.removeEventListener('abort', handleAbort);
        onRunningChange?.(false);
      };

      const finishMessage = (messageId) => {
        if (!messageId) return;
        controller.enqueue({ type: 'finish', messageId });
      };

      const enqueueMessage = (responseText, { terminal = false } = {}) => {
        if (settled || !responseText) return;
        const messageId = nextMessageId();
        const textId = `${messageId}-text`;
        lastMessageId = messageId;
        controller.enqueue({ type: 'start', messageId });
        controller.enqueue({ type: 'text-start', id: textId });
        controller.enqueue({ type: 'text-delta', id: textId, delta: responseText });
        controller.enqueue({ type: 'text-end', id: textId });
        if (terminal) {
          finishMessage(messageId);
        }
      };

      const settleFinish = () => {
        if (settled) return;
        settled = true;
        cleanup();
        finishMessage(lastMessageId);
        controller.close();
      };

      const settleWithError = (responseText) => {
        if (settled) return;
        enqueueMessage(responseText, { terminal: true });
        settled = true;
        cleanup();
        controller.close();
      };

      const handleMessage = (event) => {
        if (settled) return;

        let payload;
        try {
          payload = JSON.parse(event.data);
        } catch {
          enqueueMessage(event.data);
          return;
        }

        switch (payload.type) {
          case 'text':
            enqueueMessage(payload.content || '');
            break;
          case 'tool_call':
            enqueueMessage(getToolStatusText(payload.name));
            break;
          case 'tool_result':
            break;
          case 'complete':
            if (payload.response && !lastMessageId) {
              enqueueMessage(payload.response, { terminal: true });
              settled = true;
              cleanup();
              controller.close();
              break;
            }
            settleFinish();
            break;
          case 'error':
            settleWithError(payload.content || 'Agent error');
            break;
          default:
            enqueueMessage(event.data);
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
        controller.close();
      };

      ws.addEventListener('message', handleMessage);
      ws.addEventListener('error', handleError);
      ws.addEventListener('close', handleClose);
      signal?.addEventListener('abort', handleAbort);

      onRunningChange?.(true);
      ws.send(JSON.stringify({ message: text }));
    },
  });
}

function waitForSocketOpen(ws, signal) {
  if (!ws) {
    return Promise.reject(new Error('Socket is not available'));
  }

  if (ws.readyState === WebSocket.OPEN) {
    return Promise.resolve(ws);
  }

  if (ws.readyState !== WebSocket.CONNECTING) {
    return Promise.reject(new Error('Socket is not available'));
  }

  return new Promise((resolve, reject) => {
    const cleanup = () => {
      ws.removeEventListener('open', handleOpen);
      ws.removeEventListener('error', handleError);
      ws.removeEventListener('close', handleClose);
      signal?.removeEventListener('abort', handleAbort);
    };
    const handleOpen = () => {
      cleanup();
      resolve(ws);
    };
    const handleError = () => {
      cleanup();
      reject(new Error('Socket connection failed'));
    };
    const handleClose = () => {
      cleanup();
      reject(new Error('Socket closed'));
    };
    const handleAbort = () => {
      cleanup();
      reject(new DOMException('Aborted', 'AbortError'));
    };

    ws.addEventListener('open', handleOpen);
    ws.addEventListener('error', handleError);
    ws.addEventListener('close', handleClose);
    signal?.addEventListener('abort', handleAbort);
  });
}

function createCliAgentAdapter({ wsRef, onRunningChange }) {
  return {
    async sendMessage({ message, signal }) {
      const text = getMessageText(message).trim();
      let ws = wsRef.current;

      try {
        ws = await waitForSocketOpen(ws, signal);
      } catch {
        return new ReadableStream({
          start(controller) {
            enqueueTextResponse(
              controller,
              `response-${Date.now()}`,
              'Policy agent connection is unavailable.',
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
  { notice, onRunningChange },
  ref,
) {
  const { sendMessage, isStreaming } = useChat();
  const chatStore = useChatStore();
  const messageIds = useMessageIds();
  const inputDisabled = isStreaming;
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
        <ChatMessage messageId={params.id} sx={messageSx}>
          <ChatMessageContent partrenderers={{
            reasoning: ({ part }) => <ReasoningPart part={part} />,
            'dynamic-tool': ({ part }) => (
              <ToolPart
                part={part}
                onApprove={() => {}} // No-op since backend doesn't support approvals
                onDeny={() => {}}
              />
            ),
          }} />
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
          placeholder="Type your command here..."
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
  { wsRef, notice, onRunningChange },
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
          width: '100%',
          height: '100%',
          minHeight: 0,
          border: '1px solid',
          borderColor: 'divider',
          borderRadius: 1,
          overflow: 'hidden',
          boxSizing: 'border-box',
          '& .MuiChatConversation-root': {
            flex: 1,
            minHeight: 0,
          },
          '& .MuiChatMessageList-root': {
            flex: 1,
            minHeight: 0,
            overflowY: 'auto',
          },
          '*, *::before, *::after': { boxSizing: 'inherit' },
        }}
      >
        <ChatbotInner
          ref={ref}
          notice={notice}
          onRunningChange={onRunningChange}
        />
      </Box>
    </ChatProvider>
  );
});

export default Chatbot;
