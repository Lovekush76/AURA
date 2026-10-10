/**
 * Aura Assistant - Centralized API & Session Configuration
 * Resolves Bearer API token from VITE_AURA_API_KEY environment variable (with local default)
 * and maintains a persistent browser session ID for multi-turn ContextEngine isolation.
 */

export const getAuraApiKey = (): string => {
  const envKey = (import.meta as unknown as { env?: Record<string, string> }).env?.VITE_AURA_API_KEY;
  return envKey && envKey.trim() ? envKey.trim() : 'aura_sec_default_change_me';
};

export const getAuthHeaders = (): Record<string, string> => ({
  'Content-Type': 'application/json',
  Authorization: `Bearer ${getAuraApiKey()}`
});

export const getAuraSessionId = (): string => {
  if (typeof window === 'undefined') return 'default_session';
  try {
    let sid = window.localStorage.getItem('aura_session_id');
    if (!sid) {
      sid = `session_${Math.random().toString(36).substring(2, 10)}`;
      window.localStorage.setItem('aura_session_id', sid);
    }
    return sid;
  } catch {
    return 'default_session';
  }
};
