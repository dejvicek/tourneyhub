import type { ReactNode } from "react";

interface AuthLayoutProps {
  title: string;
  lead: string;
  children: ReactNode;
}

/** The account screens: one narrow column on a card, centred from tablet up. */
export function AuthLayout({ title, lead, children }: AuthLayoutProps) {
  return (
    <section className="mx-auto w-full max-w-md space-y-6">
      <header className="space-y-2">
        <h1 className="font-display text-display-title">{title}</h1>
        <p className="text-body-lg text-muted-foreground">{lead}</p>
      </header>
      <div className="space-y-6 md:rounded-lg md:border md:border-border-surface md:bg-card md:p-6">
        {children}
      </div>
    </section>
  );
}
