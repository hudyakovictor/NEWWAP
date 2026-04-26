import React from "react";

export function Page({
  title,
  subtitle,
  actions,
  children,
}: {
  title: string;
  subtitle?: string;
  actions?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div className="flex-1 flex flex-col min-h-0 overflow-hidden">
      <div className="flex items-center justify-between px-4 h-12 border-b border-line shrink-0 bg-bg-deep/50">
        <div>
          <div className="text-sm font-semibold text-white">{title}</div>
          {subtitle && <div className="text-[11px] text-muted -mt-0.5">{subtitle}</div>}
        </div>
        <div className="flex items-center gap-2">{actions}</div>
      </div>
      <div className="flex-1 overflow-auto p-4">{children}</div>
    </div>
  );
}

export function PanelCard({
  title,
  children,
  className = "",
  actions,
}: {
  title?: string;
  children: React.ReactNode;
  className?: string;
  actions?: React.ReactNode;
}) {
  return (
    <div className={`bg-bg-panel border border-line rounded-md ${className}`}>
      {title && (
        <div className="flex items-center justify-between px-3 h-9 border-b border-line">
          <div className="text-[11px] uppercase tracking-widest text-muted">{title}</div>
          <div>{actions}</div>
        </div>
      )}
      <div className="p-3">{children}</div>
    </div>
  );
}
