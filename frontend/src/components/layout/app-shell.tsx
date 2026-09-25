"use client";

import { useState } from "react";
import { Sidebar } from "./sidebar";
import { Topbar } from "./topbar";
import { BottomNav } from "./bottom-nav";
import { ScreenWatermark } from "@/components/crm/screen-watermark";
import { cn } from "@/lib/utils";

export function AppShell({ children }: { children: React.ReactNode }) {
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  return (
    <div>
      <ScreenWatermark />
      <Sidebar collapsed={collapsed} mobileOpen={mobileOpen} onToggle={() => setCollapsed((v) => !v)} onMobileClose={() => setMobileOpen(false)} />
      <div className={cn("min-h-screen transition-[margin] duration-200", collapsed ? "lg:ml-[76px]" : "lg:ml-[248px]")}>
        <Topbar onMenu={() => setMobileOpen(true)} />
        {/* pb-20 auf Mobile, damit Inhalte nicht hinter der neuen BottomNav
         * verschwinden - ab lg (wo die BottomNav per lg:hidden ausgeblendet
         * ist) wieder das urspruengliche p-8. */}
        <main className="mx-auto max-w-[1600px] p-5 pb-20 lg:p-8">{children}</main>
      </div>
      <BottomNav onMenu={() => setMobileOpen(true)} />
    </div>
  );
}
