import type { ReactNode } from "react";

interface SettingsSectionProps {
  id: string;
  title: string;
  description?: string;
  children: ReactNode;
}

/** One card of the settings screen, named by its heading for screen readers. */
export function SettingsSection({
  id,
  title,
  description,
  children,
}: SettingsSectionProps) {
  return (
    <section
      aria-labelledby={id}
      className="space-y-4 rounded-lg border border-border-surface bg-card p-4 text-card-foreground md:p-6"
    >
      <header className="space-y-1">
        <h2 id={id} className="font-display text-display-section">
          {title}
        </h2>
        {description !== undefined && (
          <p className="text-body-md text-muted-foreground">{description}</p>
        )}
      </header>
      {children}
    </section>
  );
}
