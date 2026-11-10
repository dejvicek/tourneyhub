import type { ReactNode } from "react";

interface ScreenHeaderProps {
  kicker?: string;
  title: string;
  subtitle?: string;
  children?: ReactNode;
}

/** The screen's heading block: kicker, title and subtitle (Display/Title). */
export function ScreenHeader({
  kicker,
  title,
  subtitle,
  children,
}: ScreenHeaderProps) {
  return (
    <header className="space-y-1">
      {kicker !== undefined && (
        <p className="text-caption font-bold text-muted-foreground">{kicker}</p>
      )}
      <h1 className="font-display text-display-screen md:text-display-title">
        {title}
      </h1>
      {subtitle !== undefined && (
        <p className="text-body-md text-muted-foreground">{subtitle}</p>
      )}
      {children}
    </header>
  );
}
