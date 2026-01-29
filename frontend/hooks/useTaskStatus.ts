'use client';

import { useState, useCallback } from 'react';
import { useSSE } from './useSSE';
import type { TaskStatusEnum, SSENotificationEvent } from '@/types';

interface UseTaskStatusOptions {
  taskId: number;
  onStatusChange?: (status: TaskStatusEnum, phase?: string) => void;
  onCompleted?: () => void;
  onError?: (message: string) => void;
}

interface UseTaskStatusReturn {
  status: TaskStatusEnum;
  phase: string | null;
  errorMessage: string | null;
  isConnected: boolean;
}

export function useTaskStatus(options: UseTaskStatusOptions): UseTaskStatusReturn {
  const { taskId, onStatusChange, onCompleted, onError } = options;

  const [status, setStatus] = useState<TaskStatusEnum>('PENDING');
  const [phase, setPhase] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const handleMessage = useCallback(
    (event: SSENotificationEvent) => {
      if (event.task_id !== taskId) return;

      setStatus(event.status);
      setPhase(event.phase || null);

      if (event.error_message) {
        setErrorMessage(event.error_message);
      }

      onStatusChange?.(event.status, event.phase);

      if (event.status === 'COMPLETED') {
        onCompleted?.();
      } else if (event.status === 'ERROR') {
        onError?.(event.error_message || '不明なエラー');
      }
    },
    [taskId, onStatusChange, onCompleted, onError]
  );

  const { isConnected } = useSSE({
    onMessage: handleMessage,
  });

  return {
    status,
    phase,
    errorMessage,
    isConnected,
  };
}
