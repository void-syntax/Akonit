"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
} from "react";

export type ToastType = "success" | "error" | "info";

export interface ToastItem {
  id: string;
  message: string;
  type: ToastType;
}

interface ToastContextValue {
  addToast: (message: string, type?: ToastType) => void;
}

const ToastContext = createContext<ToastContextValue>({
  addToast: () => undefined,
});

let _idCounter = 0;
function nextId() {
  return `toast-${++_idCounter}`;
}

// Internal state lives in a module-level ref so addToast can be called from
// outside React components (e.g. API error handlers) without needing the hook.
let _dispatch: ((message: string, type?: ToastType) => void) | null = null;

/** Call from anywhere to show a toast without needing the hook. */
export function showToast(message: string, type: ToastType = "info") {
  _dispatch?.(message, type);
}

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const timers = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map());

  const addToast = useCallback((message: string, type: ToastType = "info") => {
    const item: ToastItem = { id: nextId(), message, type };
    setToasts((prev) => [...prev, item]);

    const timer = setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== item.id));
      timers.current.delete(item.id);
    }, 4000);
    timers.current.set(item.id, timer);
  }, []);

  // Register the module-level dispatcher so showToast() works outside React.
  useEffect(() => {
    _dispatch = addToast;
    return () => {
      _dispatch = null;
    };
  }, [addToast]);

  // Clean up any pending timers on unmount.
  useEffect(() => {
    return () => {
      timers.current.forEach(clearTimeout);
    };
  }, []);

  const dismiss = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
    const timer = timers.current.get(id);
    if (timer !== undefined) {
      clearTimeout(timer);
      timers.current.delete(id);
    }
  }, []);

  return (
    <ToastContext.Provider value={{ addToast }}>
      {children}
      <Toasts toasts={toasts} onDismiss={dismiss} />
    </ToastContext.Provider>
  );
}

/** Hook for components that want to fire toasts imperatively. */
export function useToast() {
  return useContext(ToastContext);
}

// ─── Rendered stack ──────────────────────────────────────────────────────────

function toastIcon(type: ToastType) {
  if (type === "success") return "✓";
  if (type === "error") return "✕";
  return "ℹ";
}

interface ToastsProps {
  toasts: ToastItem[];
  onDismiss: (id: string) => void;
}

export function Toasts({ toasts, onDismiss }: ToastsProps) {
  if (toasts.length === 0) return null;

  return (
    <div className="toast-stack" role="region" aria-label="Notifications" aria-live="polite">
      {toasts.map((t) => (
        <div
          key={t.id}
          className={`toast toast-${t.type}`}
          role="status"
          aria-atomic="true"
        >
          <span className="toast-icon" aria-hidden="true">
            {toastIcon(t.type)}
          </span>
          <span className="toast-message">{t.message}</span>
          <button
            className="toast-close"
            onClick={() => onDismiss(t.id)}
            aria-label="Dismiss notification"
          >
            ×
          </button>
        </div>
      ))}
    </div>
  );
}
