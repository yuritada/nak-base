'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import type { SSENotificationEvent } from '@/types';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

interface UseSSEOptions {
  onMessage?: (event: SSENotificationEvent) => void;
  onError?: (error: Event) => void;
  onOpen?: () => void;
  reconnectInterval?: number;
  maxRetries?: number;
}

interface UseSSEReturn {
  isConnected: boolean;
  lastEvent: SSENotificationEvent | null;
  error: string | null;
  reconnect: () => void;
  disconnect: () => void;
}

export function useSSE(options: UseSSEOptions = {}): UseSSEReturn {
  const {
    onMessage,
    onError,
    onOpen,
    reconnectInterval = 3000,
    maxRetries = 5,
  } = options;

  const [isConnected, setIsConnected] = useState(false);
  const [lastEvent, setLastEvent] = useState<SSENotificationEvent | null>(null);
  const [error, setError] = useState<string | null>(null);

  const eventSourceRef = useRef<EventSource | null>(null);
  const retryCountRef = useRef(0);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  const connect = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
    }

    try {
      const eventSource = new EventSource(`${API_URL}/api/stream/notifications`);
      eventSourceRef.current = eventSource;

      eventSource.onopen = () => {
        setIsConnected(true);
        setError(null);
        retryCountRef.current = 0;
        onOpen?.();
      };

      eventSource.onmessage = (event) => {
        try {
          const data: SSENotificationEvent = JSON.parse(event.data);
          setLastEvent(data);
          onMessage?.(data);
        } catch (e) {
          console.error('Failed to parse SSE message:', e);
        }
      };

      eventSource.onerror = (event) => {
        setIsConnected(false);
        eventSource.close();
        onError?.(event);

        if (retryCountRef.current < maxRetries) {
          retryCountRef.current += 1;
          setError(`接続が切断されました。再接続中... (${retryCountRef.current}/${maxRetries})`);

          reconnectTimeoutRef.current = setTimeout(() => {
            connect();
          }, reconnectInterval);
        } else {
          setError('接続に失敗しました。ページをリロードしてください。');
        }
      };
    } catch (e) {
      setError('SSE接続の初期化に失敗しました');
      console.error('SSE initialization error:', e);
    }
  }, [onMessage, onError, onOpen, reconnectInterval, maxRetries]);

  const disconnect = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
    }
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }
    setIsConnected(false);
    retryCountRef.current = 0;
  }, []);

  const reconnect = useCallback(() => {
    disconnect();
    retryCountRef.current = 0;
    connect();
  }, [connect, disconnect]);

  useEffect(() => {
    connect();
    return () => {
      disconnect();
    };
  }, [connect, disconnect]);

  return {
    isConnected,
    lastEvent,
    error,
    reconnect,
    disconnect,
  };
}
