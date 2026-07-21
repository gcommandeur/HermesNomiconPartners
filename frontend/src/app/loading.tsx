import { Skeleton } from "@/components/ui/skeleton";

export default function Loading() {
  return <div className="space-y-4"><Skeleton className="h-8 w-64" /><Skeleton className="h-4 w-96 max-w-full" /><div className="grid grid-cols-1 gap-3 pt-5 sm:grid-cols-2 xl:grid-cols-3">{Array.from({ length: 6 }).map((_, index) => <Skeleton key={index} className="h-32" />)}</div></div>;
}
