"use client";

import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { SignInButton, SignUpButton, useAuth, useUser } from "@clerk/nextjs";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8123";
const clerkConfigured = Boolean(process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY);

type Profile = {
  user_id: string;
  username: string;
  display_name: string;
};

type Conversation = {
  conversation_id: string;
  recipient: Profile;
  last_message: string;
  last_sender_id: string;
  updated_at: string;
  is_last_message_from_me: boolean;
  disappearing_enabled: boolean;
  disappearing_seconds: number;
};

type ConversationSettings = {
  conversation_id: string;
  disappearing_enabled: boolean;
  disappearing_seconds: number;
};

const DISAPPEARING_OPTIONS = [
  { value: 10, label: "10 seconds" },
  { value: 600, label: "10 minutes" },
  { value: 3_600, label: "1 hour" },
  { value: 21_600, label: "6 hours" },
  { value: 36_000, label: "10 hours" },
  { value: 86_400, label: "24 hours" },
];

function disappearingLabel(seconds: number) {
  return DISAPPEARING_OPTIONS.find((option) => option.value === seconds)?.label || `${seconds} seconds`;
}

type Message = {
  message_id: string;
  sender_id: string;
  content: string;
  created_at: string;
  expires_at: string | null;
  is_from_me: boolean;
};

function GuestMessagesFlow({ onBack }: { onBack: () => void }) {
  return (
    <section className="dm-flow" aria-labelledby="dm-title">
      <button className="back-link" type="button" onClick={onBack}>
        <span aria-hidden="true">&larr;</span> Back to toolkit
      </button>
      <div className="dm-guest-card">
        <span className="dm-icon" aria-hidden="true">↔</span>
        <p className="eyebrow">Private conversations</p>
        <h2 id="dm-title">Sign in to message someone safely.</h2>
        <p>
          Direct messages are private to signed-in Aegis accounts. You can still use the SOS tools and chat companions as a guest.
        </p>
        {clerkConfigured ? (
          <div className="dm-auth-actions">
            <SignInButton mode="modal">
              <button className="dm-primary-button" type="button">Sign in</button>
            </SignInButton>
            <SignUpButton mode="modal">
              <button className="dm-secondary-button" type="button">Create account</button>
            </SignUpButton>
          </div>
        ) : (
          <p className="dm-muted">Account setup is not configured yet.</p>
        )}
      </div>
    </section>
  );
}

export default function DirectMessagesFlow({ onBack }: { onBack: () => void }) {
  if (!clerkConfigured) return <GuestMessagesFlow onBack={onBack} />;
  return <AuthenticatedMessagesFlow onBack={onBack} />;
}

function AuthenticatedMessagesFlow({ onBack }: { onBack: () => void }) {
  const { getToken } = useAuth();
  const { isLoaded, isSignedIn, user } = useUser();
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [selected, setSelected] = useState<Conversation | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [search, setSearch] = useState("");
  const [results, setResults] = useState<Profile[]>([]);
  const [draft, setDraft] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isSending, setIsSending] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [settingsEnabled, setSettingsEnabled] = useState(false);
  const [settingsSeconds, setSettingsSeconds] = useState("21600");
  const [isSavingSettings, setIsSavingSettings] = useState(false);
  const [selectionMode, setSelectionMode] = useState(false);
  const [selectedMessageIds, setSelectedMessageIds] = useState<string[]>([]);
  const [isDeleting, setIsDeleting] = useState(false);
  const pendingMessageRef = useRef<{ content: string; clientMessageId: string } | null>(null);

  const displayName = useMemo(
    () => user?.fullName || user?.username || "Aegis user",
    [user],
  );
  const username = user?.username || user?.id.replace(/^user_/, "aegisuser");

  const request = useCallback(async <T,>(path: string, options: RequestInit = {}): Promise<T> => {
    const method = (options.method || "GET").toUpperCase();
    const backendUnavailable = `Aegis cannot reach the backend at ${API_BASE_URL}. Start the backend on port 8123 and try again.`;
    const send = async (token: string) => fetch(`${API_BASE_URL}${path}`, {
      ...options,
      cache: "no-store",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
        ...(options.headers || {}),
      },
    });

    let token = await getToken();
    if (!token) throw new Error("Your sign-in session is not ready. Please sign in again.");

    let response: Response;
    try {
      response = await send(token);
    } catch {
      // GET requests are safe to retry after a short-lived server restart or
      // network hiccup. Do not blindly retry POST requests because the server
      // may have accepted the write before the browser lost the response.
      if (method !== "GET") throw new Error(backendUnavailable);
      await new Promise((resolve) => window.setTimeout(resolve, 250));
      try {
        response = await send(token);
      } catch {
        throw new Error(backendUnavailable);
      }
    }
    // Clerk normally refreshes tokens automatically. A long-open tab or an
    // account switch can leave one cached token stale, so recover once before
    // asking the user to sign in again.
    if (response.status === 401) {
      const freshToken = await getToken({ skipCache: true });
      if (freshToken) {
        token = freshToken;
        response = await send(token);
      }
    }

    const body = await response.json().catch(() => null);
    if (!response.ok) {
      throw new Error(typeof body?.detail === "string" ? body.detail : "Aegis could not complete that request.");
    }
    return body as T;
  }, [getToken]);

  const loadConversations = useCallback(async () => {
    const loaded = await request<Conversation[]>("/dm/conversations");
    setConversations(loaded);
    setSelected((current) => {
      const next = !current
        ? (loaded[0] || null)
        : (loaded.find((item) => item.conversation_id === current.conversation_id) || current);
      if (next && (!current
        || next.conversation_id !== current.conversation_id
        || next.disappearing_enabled !== current.disappearing_enabled
        || next.disappearing_seconds !== current.disappearing_seconds)) {
        setSettingsEnabled(next.disappearing_enabled);
        setSettingsSeconds(String(next.disappearing_seconds || 21600));
      }
      return next;
    });
  }, [request]);

  useEffect(() => {
    if (!isLoaded || !isSignedIn || !user || !username) return;
    let active = true;
    const loadAccount = async () => {
      setIsLoading(true);
      setError("");
      try {
        await Promise.all([
          request<Profile>("/dm/profile", {
            method: "POST",
            body: JSON.stringify({ username, display_name: displayName }),
          }),
          loadConversations(),
        ]);
      } catch (requestError: unknown) {
        if (active) setError(requestError instanceof Error ? requestError.message : "Aegis could not load private messages.");
      } finally {
        if (active) setIsLoading(false);
      }
    };
    void loadAccount();
    return () => { active = false; };
  }, [displayName, isLoaded, isSignedIn, loadConversations, request, user, username]);

  const loadMessages = useCallback(async (conversationId: string) => {
    const loaded = await request<Message[]>(`/dm/conversations/${conversationId}/messages`);
    setMessages(loaded);
  }, [request]);

  useEffect(() => {
    if (!selected) return;
    let active = true;
    let socket: WebSocket | null = null;
    let fallbackTimer: number | null = null;
    const refresh = async () => {
      try {
        const loaded = await request<Message[]>(`/dm/conversations/${selected.conversation_id}/messages`);
        if (active) setMessages(loaded);
      } catch (requestError: unknown) {
        if (active) setError(requestError instanceof Error ? requestError.message : "Aegis could not refresh this conversation.");
      }
    };
    void refresh();
    const startFallbackPolling = () => {
      if (fallbackTimer === null) fallbackTimer = window.setInterval(() => { void refresh(); }, 4_000);
    };
    const connectRealtime = async () => {
      try {
        const token = await getToken({ skipCache: true });
        if (!token || !active) {
          startFallbackPolling();
          return;
        }
        const socketBase = API_BASE_URL.replace(/^http:/, "ws:").replace(/^https:/, "wss:");
        socket = new WebSocket(`${socketBase}/dm/conversations/${selected.conversation_id}/stream`);
        socket.onopen = () => {
          socket?.send(JSON.stringify({ token }));
          if (fallbackTimer !== null) {
            window.clearInterval(fallbackTimer);
            fallbackTimer = null;
          }
        };
        socket.onmessage = (event) => {
          try {
            const payload = JSON.parse(event.data) as {
              type?: string;
              message?: Message;
              settings?: ConversationSettings;
              deleted_message_ids?: string[];
            };
            if (payload.type === "message" && payload.message) {
              setMessages((current) => current.some((message) => message.message_id === payload.message?.message_id)
                ? current
                : [...current, payload.message as Message]);
              void loadConversations();
              return;
            }
            if (payload.type === "settings" && payload.settings) {
              const settings = payload.settings;
              setSelected((current) => current?.conversation_id === settings.conversation_id
                ? { ...current, ...settings }
                : current);
              setConversations((current) => current.map((conversation) => conversation.conversation_id === settings.conversation_id
                ? { ...conversation, ...settings }
                : conversation));
              return;
            }
            if (payload.type === "messages_deleted" && payload.deleted_message_ids) {
              const deletedIds = new Set(payload.deleted_message_ids);
              setMessages((current) => current.filter((message) => !deletedIds.has(message.message_id)));
              setSelectedMessageIds((current) => current.filter((messageId) => !deletedIds.has(messageId)));
              void loadConversations();
            }
          } catch {
            // Keep the conversation usable if a malformed event is received.
          }
        };
        socket.onerror = () => startFallbackPolling();
        socket.onclose = () => {
          if (active) startFallbackPolling();
        };
      } catch {
        startFallbackPolling();
      }
    };
    void connectRealtime();
    return () => {
      active = false;
      if (fallbackTimer !== null) window.clearInterval(fallbackTimer);
      socket?.close();
    };
  }, [getToken, loadConversations, loadMessages, request, selected]);

  useEffect(() => {
    const cleanupTimer = window.setInterval(() => {
      const now = Date.now();
      setMessages((current) => {
        const next = current.filter((message) => !message.expires_at || Date.parse(message.expires_at) > now);
        return next.length === current.length ? current : next;
      });
    }, 15_000);
    return () => window.clearInterval(cleanupTimer);
  }, []);

  if (!isLoaded) {
    return <section className="dm-flow"><p className="dm-muted">Loading account…</p></section>;
  }

  if (!isSignedIn || !user) {
    return <GuestMessagesFlow onBack={onBack} />;
  }

  async function searchUsers(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    try {
      setResults(await request<Profile[]>(`/dm/users?query=${encodeURIComponent(search.trim())}`));
    } catch (requestError: unknown) {
      setError(requestError instanceof Error ? requestError.message : "Aegis could not search for that user.");
    }
  }

  async function openConversation(profile: Profile) {
    setError("");
    setNotice("");
    try {
      const conversation = await request<Conversation>("/dm/conversations", {
        method: "POST",
        body: JSON.stringify({ username: profile.username }),
      });
      setSelected(conversation);
      setSettingsEnabled(conversation.disappearing_enabled);
      setSettingsSeconds(String(conversation.disappearing_seconds || 21600));
      setIsSettingsOpen(false);
      setSelectionMode(false);
      setSelectedMessageIds([]);
      setResults([]);
      setSearch("");
      await loadConversations();
      await loadMessages(conversation.conversation_id);
    } catch (requestError: unknown) {
      setError(requestError instanceof Error ? requestError.message : "Aegis could not start that conversation.");
    }
  }

  function selectConversation(conversation: Conversation) {
    setSelected(conversation);
    setSettingsEnabled(conversation.disappearing_enabled);
    setSettingsSeconds(String(conversation.disappearing_seconds || 21600));
    setIsSettingsOpen(false);
    setSelectionMode(false);
    setSelectedMessageIds([]);
  }

  async function sendMessage(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selected || !draft.trim()) return;
    setIsSending(true);
    setError("");
    const content = draft.trim();
    const pending = pendingMessageRef.current;
    const clientMessageId = pending?.content === content
      ? pending.clientMessageId
      : (globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(36).slice(2)}`);
    pendingMessageRef.current = { content, clientMessageId };
    try {
      const sent = await request<Message>(`/dm/conversations/${selected.conversation_id}/messages`, {
        method: "POST",
        body: JSON.stringify({ content, client_message_id: clientMessageId }),
      });
      pendingMessageRef.current = null;
      setDraft("");
      setNotice("Message sent.");
      setMessages((current) => current.some((message) => message.message_id === sent.message_id)
        ? current
        : [...current, sent]);
      void loadConversations();
    } catch (requestError: unknown) {
      setError(requestError instanceof Error ? requestError.message : "Aegis could not send that message.");
    } finally {
      setIsSending(false);
    }
  }

  function toggleMessageSelection(messageId: string) {
    setSelectedMessageIds((current) => current.includes(messageId)
      ? current.filter((id) => id !== messageId)
      : [...current, messageId]);
  }

  async function saveConversationSettings() {
    if (!selected) return;
    const seconds = Number(settingsSeconds);
    if (!Number.isSafeInteger(seconds) || seconds < 10 || !DISAPPEARING_OPTIONS.some((option) => option.value === seconds)) {
      setError("Choose one of the available timers, starting at 10 seconds.");
      return;
    }
    setIsSavingSettings(true);
    setError("");
    try {
      const saved = await request<ConversationSettings>(`/dm/conversations/${selected.conversation_id}/settings`, {
        method: "PATCH",
        body: JSON.stringify({ enabled: settingsEnabled, seconds }),
      });
      setSelected((current) => current?.conversation_id === saved.conversation_id
        ? { ...current, ...saved }
        : current);
      setConversations((current) => current.map((conversation) => conversation.conversation_id === saved.conversation_id
        ? { ...conversation, ...saved }
        : conversation));
      setSettingsSeconds(String(saved.disappearing_seconds));
      setSettingsEnabled(saved.disappearing_enabled);
      setIsSettingsOpen(false);
      setNotice(saved.disappearing_enabled
        ? `New messages will disappear after ${disappearingLabel(saved.disappearing_seconds)}.`
        : "Disappearing messages are turned off.");
    } catch (requestError: unknown) {
      setError(requestError instanceof Error ? requestError.message : "Aegis could not save that setting.");
    } finally {
      setIsSavingSettings(false);
    }
  }

  async function deleteSelectedMessages() {
    if (!selected || selectedMessageIds.length === 0) return;
    setIsDeleting(true);
    setError("");
    try {
      const deleted = await request<{ deleted_message_ids: string[] }>(`/dm/conversations/${selected.conversation_id}/messages`, {
        method: "DELETE",
        body: JSON.stringify({ message_ids: selectedMessageIds }),
      });
      const deletedIds = new Set(deleted.deleted_message_ids);
      setMessages((current) => current.filter((message) => !deletedIds.has(message.message_id)));
      setSelectedMessageIds([]);
      setSelectionMode(false);
      setNotice(deleted.deleted_message_ids.length === 1
        ? "Message deleted."
        : `${deleted.deleted_message_ids.length} messages deleted.`);
      void loadConversations();
    } catch (requestError: unknown) {
      setError(requestError instanceof Error ? requestError.message : "Aegis could not delete those messages.");
    } finally {
      setIsDeleting(false);
    }
  }

  return (
    <section className="dm-flow" aria-labelledby="dm-title">
      <div className="dm-heading-row">
        <button className="back-link" type="button" onClick={onBack}>
          <span aria-hidden="true">&larr;</span> Back to toolkit
        </button>
        <span className="dm-account-chip">@{username}</span>
      </div>
      <div className="dm-header-copy">
        <p className="eyebrow">Private conversations</p>
        <h2 id="dm-title">A quiet line to someone you trust.</h2>
        <p>Search by username to start a private conversation. Messages are only available to the two signed-in accounts.</p>
      </div>

      <div className="dm-layout">
        <aside className="dm-sidebar" aria-label="Conversations and user search">
          <form className="dm-search-form" onSubmit={searchUsers}>
            <label htmlFor="dm-search">Find a username</label>
            <div className="dm-search-row">
              <input id="dm-search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="e.g. isha" maxLength={64} />
              <button className="dm-small-button" type="submit">Search</button>
            </div>
          </form>
          {results.length > 0 && (
            <div className="dm-search-results">
              {results.map((profile) => (
                <button className="dm-profile-result" type="button" key={profile.user_id} onClick={() => void openConversation(profile)}>
                  <span className="dm-profile-avatar" aria-hidden="true">{profile.username.slice(0, 1).toUpperCase()}</span>
                  <span><strong>{profile.display_name}</strong><small>@{profile.username}</small></span>
                </button>
              ))}
            </div>
          )}
          <div className="dm-list-heading"><span>Your conversations</span><button type="button" onClick={() => void loadConversations()} aria-label="Refresh conversations">↻</button></div>
          {isLoading && <p className="dm-muted">Loading…</p>}
          {!isLoading && conversations.length === 0 && <p className="dm-muted">No private conversations yet.</p>}
          <div className="dm-conversation-list">
            {conversations.map((conversation) => (
              <button
                className={`dm-conversation-item ${selected?.conversation_id === conversation.conversation_id ? "is-selected" : ""}`}
                type="button"
                key={conversation.conversation_id}
                onClick={() => selectConversation(conversation)}
              >
                <span className="dm-profile-avatar" aria-hidden="true">{conversation.recipient.username.slice(0, 1).toUpperCase()}</span>
                <span><strong>{conversation.recipient.display_name}</strong><small>@{conversation.recipient.username}</small><em>{conversation.last_message || "Conversation started"}</em></span>
              </button>
            ))}
          </div>
        </aside>

        <div className="dm-conversation-panel">
          {selected ? (
            <>
              <div className="dm-conversation-heading">
                <span className="dm-profile-avatar" aria-hidden="true">{selected.recipient.username.slice(0, 1).toUpperCase()}</span>
                <div><strong>{selected.recipient.display_name}</strong><small>@{selected.recipient.username}</small></div>
                <div className="dm-conversation-tools">
                  <button className={`dm-tool-button ${selected.disappearing_enabled ? "is-active" : ""}`} type="button" onClick={() => setIsSettingsOpen((current) => !current)}>
                    {selected.disappearing_enabled ? `${disappearingLabel(selected.disappearing_seconds)} disappearing` : "Disappearing"}
                  </button>
                  <button className={`dm-tool-button ${selectionMode ? "is-active" : ""}`} type="button" onClick={() => {
                    setSelectionMode((current) => !current);
                    setSelectedMessageIds([]);
                  }}>
                    {selectionMode ? "Cancel" : "Select"}
                  </button>
                </div>
              </div>
              {isSettingsOpen && (
                <div className="dm-settings-panel" role="region" aria-label="Disappearing message settings">
                  <label className="dm-settings-toggle">
                    <input type="checkbox" checked={settingsEnabled} onChange={(event) => setSettingsEnabled(event.target.checked)} />
                    <span><strong>Disappearing messages</strong><small>Only messages sent after saving this setting will expire.</small></span>
                  </label>
                  <div className="dm-settings-row">
                    <label htmlFor="dm-disappearing-duration">Delete new messages after</label>
                    <select
                      id="dm-disappearing-duration"
                      value={settingsSeconds}
                      onChange={(event) => setSettingsSeconds(event.target.value)}
                    >
                      {DISAPPEARING_OPTIONS.map((option) => (
                        <option value={option.value} key={option.value}>{option.label}</option>
                      ))}
                    </select>
                  </div>
                  <p className="dm-settings-help">Choose when new messages should disappear. The minimum timer is 10 seconds.</p>
                  <button className="dm-primary-button" type="button" onClick={() => void saveConversationSettings()} disabled={isSavingSettings}>
                    {isSavingSettings ? "Saving…" : "Save settings"}
                  </button>
                </div>
              )}
              {selectionMode && (
                <div className="dm-selection-toolbar" role="toolbar" aria-label="Selected messages">
                  <span>{selectedMessageIds.length} selected</span>
                  <button className="dm-delete-button" type="button" onClick={() => void deleteSelectedMessages()} disabled={isDeleting || selectedMessageIds.length === 0}>
                    {isDeleting ? "Deleting…" : "Delete selected"}
                  </button>
                </div>
              )}
              <div className="dm-messages" data-lenis-prevent aria-live="polite">
                {messages.length === 0 && <p className="dm-empty-conversation">This is the beginning of a private conversation.</p>}
                {messages.map((message) => (
                  <div
                    className={`dm-message ${message.is_from_me ? "is-mine" : "is-theirs"} ${selectionMode ? "is-selectable" : ""} ${selectedMessageIds.includes(message.message_id) ? "is-selected" : ""}`}
                    key={message.message_id}
                    role={selectionMode ? "checkbox" : undefined}
                    aria-checked={selectionMode ? selectedMessageIds.includes(message.message_id) : undefined}
                    tabIndex={selectionMode ? 0 : undefined}
                    onClick={selectionMode ? () => toggleMessageSelection(message.message_id) : undefined}
                    onKeyDown={selectionMode ? (event) => {
                      if (event.key === "Enter" || event.key === " ") toggleMessageSelection(message.message_id);
                    } : undefined}
                  >
                    <p>{message.content}</p>
                    <time dateTime={message.created_at}>{message.is_from_me ? "You" : selected.recipient.display_name}</time>
                  </div>
                ))}
              </div>
              <form className="dm-composer" onSubmit={sendMessage}>
                <label className="sr-only" htmlFor="dm-message">Write a private message</label>
                <textarea id="dm-message" value={draft} onChange={(event) => setDraft(event.target.value)} placeholder="Write a private message…" maxLength={2_000} rows={3} />
                <button className="dm-primary-button" type="submit" disabled={isSending || !draft.trim()}>{isSending ? "Sending…" : "Send message"}</button>
              </form>
            </>
          ) : (
            <div className="dm-empty-state"><span className="dm-icon" aria-hidden="true">↔</span><h3>Choose a conversation</h3><p>Search for a signed-in Aegis user to begin.</p></div>
          )}
        </div>
      </div>
      {notice && <p className="dm-notice" role="status">{notice}</p>}
      {error && <p className="dm-error" role="alert">{error}</p>}
      <p className="dm-footnote">Private messages require an account. Do not share anything that could put you at greater risk if your device is monitored.</p>
    </section>
  );
}
