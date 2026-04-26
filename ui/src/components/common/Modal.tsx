import type { ReactNode } from "react";

export default function Modal({
  title,
  onClose,
  children,
  width = "max-w-3xl",
}: {
  title: string;
  onClose: () => void;
  children: ReactNode;
  width?: string;
}) {
  return (
    <div
      className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4"
      onClick={onClose}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className={`w-full ${width} max-h-[85vh] bg-bg-panel border border-line rounded-lg shadow-2xl flex flex-col overflow-hidden`}
      >
        <div className="flex items-center justify-between h-10 px-4 border-b border-line shrink-0">
          <div className="text-sm font-semibold text-white">{title}</div>
          <button
            onClick={onClose}
            className="w-7 h-7 rounded bg-danger/30 hover:bg-danger/60 text-white"
          >
            ×
          </button>
        </div>
        <div className="flex-1 overflow-auto p-4">{children}</div>
      </div>
    </div>
  );
}
