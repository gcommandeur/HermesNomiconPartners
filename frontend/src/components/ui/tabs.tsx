"use client";

import * as TabsPrimitive from "@radix-ui/react-tabs";
import { cn } from "@/lib/utils";

export const Tabs = TabsPrimitive.Root;
export const TabsContent = TabsPrimitive.Content;

export function TabsList({ className, ...props }: React.ComponentProps<typeof TabsPrimitive.List>) {
  return <TabsPrimitive.List className={cn("flex gap-6 border-b border-white/10", className)} {...props} />;
}

export function TabsTrigger({ className, ...props }: React.ComponentProps<typeof TabsPrimitive.Trigger>) {
  return (
      <TabsPrimitive.Trigger
      className={cn("border-b-2 border-transparent px-0 py-3 text-sm font-medium text-brand-muted transition-colors data-[state=active]:border-brand-platinum data-[state=active]:text-brand-text", className)}
      {...props}
    />
  );
}
