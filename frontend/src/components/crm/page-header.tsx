export function PageHeader({ eyebrow, title, action }: {
  eyebrow?: string;
  title: string;
  description?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="mb-7 flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
      <div>
        {eyebrow && <p className="mb-2 text-[10px] font-semibold uppercase tracking-[.22em] text-[#A7ADB7]">{eyebrow}</p>}
        <h1 className="text-2xl font-semibold tracking-[-.025em] text-[#F8FAFC] lg:text-[28px]">{title}</h1>
      </div>
      {action}
    </div>
  );
}
