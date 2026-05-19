import React, { createContext, useContext, useState, useCallback } from 'react';

interface Notification {
  id: string;
  type: 'success' | 'error' | 'warning' | 'info';
  title: string;
  message?: string;
  duration?: number;
}

interface NotificationContextType {
  notifications: Notification[];
  addNotification: (notification: Omit<Notification, 'id'>) => void;
  removeNotification: (id: string) => void;
  clearAll: () => void;
}

const NotificationContext = createContext<NotificationContextType | undefined>(undefined);

/**
 * Provider component for notification system.
 * Wraps the app to provide notification context to all children.
 */
export function NotificationProvider({ children }: { children: React.ReactNode }) {
  const [notifications, setNotifications] = useState<Notification[]>([]);

  const addNotification = useCallback((notification: Omit<Notification, 'id'>) => {
    const id = Date.now().toString();
    const newNotification: Notification = { ...notification, id };
    setNotifications((prev) => [...prev, newNotification]);

    if (notification.duration !== 0) {
      setTimeout(() => {
        removeNotification(id);
      }, notification.duration || 5000);
    }
  }, []);

  const removeNotification = useCallback((id: string) => {
    setNotifications((prev) => prev.filter((n) => n.id !== id));
  }, []);

  const clearAll = useCallback(() => {
    setNotifications([]);
  }, []);

  return (
    <NotificationContext.Provider value={{ notifications, addNotification, removeNotification, clearAll }}>
      {children}
      <NotificationDisplay notifications={notifications} onRemove={removeNotification} />
    </NotificationContext.Provider>
  );
}

/**
 * Hook to access notification functions.
 * Must be used within NotificationProvider.
 */
export function useNotifications() {
  const context = useContext(NotificationContext);
  if (!context) {
    throw new Error('useNotifications must be used within NotificationProvider');
  }
  return context;
}

function NotificationDisplay({ notifications, onRemove }: { notifications: Notification[]; onRemove: (id: string) => void }) {
  const typeColors = {
    success: 'bg-green-600',
    error: 'bg-red-600',
    warning: 'bg-yellow-600',
    info: 'bg-blue-600',
  };

  return (
    <div className="fixed top-4 right-4 z-50 flex flex-col gap-2">
      {notifications.map((notification) => (
        <div
          key={notification.id}
          className={`${typeColors[notification.type]} text-white px-4 py-3 rounded shadow-lg flex items-center gap-3 min-w-80`}
        >
          <div className="flex-1">
            <div className="font-bold">{notification.title}</div>
            {notification.message && <div className="text-sm opacity-90">{notification.message}</div>}
          </div>
          <button
            onClick={() => onRemove(notification.id)}
            className="text-white hover:opacity-70"
          >
            ✕
          </button>
        </div>
      ))}
    </div>
  );
}
