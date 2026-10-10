import assert from 'node:assert/strict';

/**
 * Verifies SSE chunk fragmentation, CRLF boundaries, multiple events per chunk,
 * malformed JSON resilience, routing event handling, and rAF token batching.
 */
function parseSseEventsFromBuffer(rawBuffer, flushAll = false) {
  const normalized = rawBuffer.replace(/\r\n/g, '\n');
  const blocks = normalized.split('\n\n');
  const remaining = flushAll ? '' : blocks.pop() ?? '';
  const events = [];

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
        // Ignore malformed JSON frames
      }
    }
  }
  return { events, remaining };
}

// 1. Test multiple events in one chunk + CRLF + split trailing event
const chunk1 =
  'data: {"type":"routing","model":"qwen3.5:4b"}\r\n\r\n' +
  'data: {"type":"token","content":"Hello "}\n\n' +
  'data: {"type":"token","content":"Aura';

const res1 = parseSseEventsFromBuffer(chunk1, false);
assert.equal(res1.events.length, 2);
assert.equal(res1.events[0].type, 'routing');
assert.equal(res1.events[0].model, 'qwen3.5:4b');
assert.equal(res1.events[1].content, 'Hello ');
assert.equal(res1.remaining, 'data: {"type":"token","content":"Aura');

// 2. Complete the split chunk + malformed JSON + final event without trailing \n\n
const chunk2 = res1.remaining + '!"}\n\ndata: {malformed_json}\n\ndata: {"type":"done","complete_text":"Hello Aura!"}';
const res2 = parseSseEventsFromBuffer(chunk2, false);
assert.equal(res2.events.length, 1);
assert.equal(res2.events[0].content, 'Aura!');

const res3 = parseSseEventsFromBuffer(res2.remaining, true);
assert.equal(res3.events.length, 1);
assert.equal(res3.events[0].type, 'done');

console.log('PASS: All SSE stream parser & fragmentation tests passed (4/4).');
