/**
 * Shared SSE Stream Parser & requestAnimationFrame Token Batcher
 * Handles split chunks, CRLF/LF boundaries, multiple events per chunk, malformed JSON,
 * explicit 'routing' / 'token' / 'done' / 'error' events, and <=1 store update per animation frame.
 */

export interface AuraSseRoutingEvent {
  type: 'routing';
  model: string;
  pinned?: boolean;
  num_ctx?: number;
  keep_alive?: number | string;
  fallback_reason?: string | null;
  channel?: string;
}

export interface AuraSseCallbacks {
  onRouting?: (event: AuraSseRoutingEvent) => void;
  onTokenBatch: (batchText: string, measuredTps: number, routedModel?: string) => void;
  onDone?: (completeText: string, routedModel?: string) => void;
  onError?: (errorMessage: string) => void;
}

export function parseSseEventsFromBuffer(
  rawBuffer: string,
  flushAll = false
): { events: Record<string, any>[]; remaining: string } {
  const normalized = rawBuffer.replace(/\r\n/g, '\n');
  const blocks = normalized.split('\n\n');
  const remaining = flushAll ? '' : blocks.pop() ?? '';
  const events: Record<string, any>[] = [];

  for (const block of blocks) {
    const trimmed = block.trim();
    if (!trimmed) continue;
    for (const line of trimmed.split('\n')) {
      const cleanLine = line.trim();
      if (!cleanLine.startsWith('data:')) continue;
      const jsonStr = cleanLine.slice(5).trim();
      if (!jsonStr || jsonStr === '[DONE]') continue;
      try {
        const parsed = JSON.parse(jsonStr);
        if (parsed && typeof parsed === 'object') {
          events.push(parsed);
        }
      } catch {
        // Ignore malformed JSON frames without crashing the stream
      }
    }
  }

  return { events, remaining };
}

export async function consumeAuraSseStream(
  response: Response,
  callbacks: AuraSseCallbacks,
  signal?: AbortSignal
): Promise<string> {
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }
  if (!response.body) {
    throw new Error('ReadableStream not supported');
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder('utf-8');
  let buffer = '';
  let fullResponse = '';
  let pendingBatch = '';
  let tokenCount = 0;
  let lastTps = 0;
  let routedModel: string | undefined;
  let rafId: number | null = null;
  const t0 = typeof performance !== 'undefined' ? performance.now() : Date.now();

  const flushPendingTokens = () => {
    if (rafId !== null && typeof cancelAnimationFrame === 'function') {
      cancelAnimationFrame(rafId);
      rafId = null;
    }
    if (pendingBatch.length > 0) {
      const toCommit = pendingBatch;
      pendingBatch = '';
      callbacks.onTokenBatch(toCommit, lastTps, routedModel);
    }
  };

  const scheduleFrameFlush = () => {
    if (rafId !== null) return;
    if (typeof requestAnimationFrame === 'function') {
      rafId = requestAnimationFrame(() => {
        rafId = null;
        flushPendingTokens();
      });
    } else {
      flushPendingTokens();
    }
  };

  const processParsedEvents = (events: Record<string, any>[]) => {
    for (const data of events) {
      if (data.type === 'routing' && typeof data.model === 'string') {
        routedModel = data.model;
        callbacks.onRouting?.(data as AuraSseRoutingEvent);
      } else if (data.type === 'token' && typeof data.content === 'string') {
        fullResponse += data.content;
        pendingBatch += data.content;
        tokenCount += Math.max(1, Math.ceil(data.content.length / 3.8));
        const now = typeof performance !== 'undefined' ? performance.now() : Date.now();
        const dtSec = Math.max(0.015, (now - t0) / 1000);
        lastTps = Math.min(395.0, Math.max(1.0, tokenCount / dtSec));
        scheduleFrameFlush();
      } else if (data.type === 'error') {
        flushPendingTokens();
        const errMsg = typeof data.error === 'string' ? data.error : 'Stream error';
        callbacks.onError?.(errMsg);
      } else if (data.type === 'done') {
        flushPendingTokens();
        callbacks.onDone?.(fullResponse, routedModel);
      }
    }
  };

  try {
    while (true) {
      if (signal?.aborted) {
        await reader.cancel().catch(() => {});
        break;
      }
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const { events, remaining } = parseSseEventsFromBuffer(buffer, false);
      buffer = remaining;
      processParsedEvents(events);
    }

    buffer += decoder.decode();
    if (buffer.trim()) {
      const { events } = parseSseEventsFromBuffer(buffer, true);
      processParsedEvents(events);
    }
    flushPendingTokens();
    return fullResponse;
  } finally {
    flushPendingTokens();
    reader.releaseLock();
  }
}
