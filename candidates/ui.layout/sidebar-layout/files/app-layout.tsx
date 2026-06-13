"use client";

type NavItem = {
  label: string;
  href: string;
};

type AppLayoutProps = {
  children: React.ReactNode;
  title?: string;
  nav?: NavItem[];
};

/**
 * 侧边栏应用布局：左侧固定导航 + 右侧内容区。保持 {children, title, nav} 契约。
 * 零外部依赖。适合后台管理类应用骨架。
 */
export function AppLayout({ children, title = "应用", nav = [] }: AppLayoutProps) {
  return (
    <div className="flex min-h-screen bg-slate-50">
      <aside className="w-56 shrink-0 border-r border-slate-200 bg-white p-4">
        <div className="mb-6 text-lg font-bold text-slate-800">{title}</div>
        <nav className="flex flex-col gap-1">
          {nav.map((item) => (
            <a
              key={item.href}
              href={item.href}
              className="rounded px-3 py-2 text-sm text-slate-600 hover:bg-slate-100 hover:text-slate-900"
            >
              {item.label}
            </a>
          ))}
        </nav>
      </aside>
      <main className="flex-1 p-6">{children}</main>
    </div>
  );
}
