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
 * 顶栏应用布局：顶部水平导航 + 下方居中内容区。保持 {children, title, nav} 契约。
 * 零外部依赖。适合内容站/营销页/简单应用骨架。
 */
export function AppLayout({ children, title = "应用", nav = [] }: AppLayoutProps) {
  return (
    <div className="min-h-screen bg-slate-50">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-5xl items-center justify-between px-6 py-3">
          <div className="text-lg font-bold text-slate-800">{title}</div>
          <nav className="flex gap-4">
            {nav.map((item) => (
              <a
                key={item.href}
                href={item.href}
                className="text-sm text-slate-600 hover:text-slate-900"
              >
                {item.label}
              </a>
            ))}
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-5xl px-6 py-8">{children}</main>
    </div>
  );
}
