export function PageHeader({ eyebrow, title, action }: {
  eyebrow?: string;
  title: string;
  description?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="mb-4 flex flex-col justify-between gap-4 sm:flex-row sm:items-end lg:mb-7">
      <div>
        {eyebrow && <p className="mb-2 text-[10px] font-semibold uppercase tracking-[.22em] text-brand-silver">{eyebrow}</p>}
        <h1 className="text-2xl font-semibold tracking-[-.025em] text-brand-text lg:text-[28px]">{title}</h1>
      </div>
      {action}
    </div>
  );
}
