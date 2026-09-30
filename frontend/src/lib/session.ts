// The current dataset ID and its token, kept together in sessionStorage so
// they live only as long as the browser tab.

const KEY = "osa.session";

export interface Session {
  id: string;
  token: string;
}

export function saveSession(session: Session): void {
  try {
    window.sessionStorage.setItem(
      KEY,
      JSON.stringify({ id: session.id, token: session.token }),
    );
  } catch {
    // Storage unavailable: behave as if nothing is stored.
  }
}

export function readSession(): Session | null {
  try {
    const raw = window.sessionStorage.getItem(KEY);
    if (raw === null) return null;
    const value: unknown = JSON.parse(raw);
    if (typeof value !== "object" || value === null) return null;
    const { id, token } = value as Record<string, unknown>;
    if (typeof id !== "string" || typeof token !== "string" || !id || !token) {
      return null;
    }
    return { id, token };
  } catch {
    return null;
  }
}

export function clearSession(): void {
  try {
    window.sessionStorage.removeItem(KEY);
  } catch {
    // Nothing to clear.
  }
}

/** The token to send for `datasetId`: only when the stored ID is that ID. */
export function tokenFor(datasetId: string): string | null {
  const session = readSession();
  return session !== null && session.id === datasetId ? session.token : null;
}
