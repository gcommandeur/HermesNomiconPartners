"use client";

import { useRouter } from "next/navigation";
import { Bell, LogOut, Menu, Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import { QuickActionMenu } from "@/components/crm/quick-action-menu";

export function Topbar({ onMenu }: { onMenu: () => void }) {
  const router = useRouter();

  async function handleLogout() {
    await fetch("/api/logout", { method: "POST" });
    router.replace("/login");
    router.refresh();
  }

  return (
    <header className="sticky top-0 z-30 flex h-16 items-center border-b border-white/10 bg-[#0D1B2E]/90 px-5 shadow-[0_10px_35px_rgba(0,0,0,.15)] backdrop-blur-xl lg:px-8">
      <button onClick={onMenu} className="mr-3 text-[#A7ADB7] lg:hidden" aria-label="Navigation öffnen"><Menu size={20} /></button>
      <div className="relative hidden w-full max-w-md sm:block">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-[#90969b]" size={16} />
        <input className="h-9 w-full rounded-md border border-white/10 bg-[#08111F]/70 pl-9 pr-3 text-sm text-white outline-none placeholder:text-[#747C89] focus:border-[#1F5FA8] focus:ring-2 focus:ring-[#1F5FA8]/20" placeholder="Kandidaten, Kanzleien, Kontakte oder Prozesse suchen" />
      </div>
      <div className="ml-auto flex items-center gap-2">
        <QuickActionMenu />
        <Button variant="ghost" size="icon" aria-label="Benachrichtigungen"><Bell size={17} /></Button>
        <button className="ml-1 flex items-center gap-2 rounded-md p-1.5 hover:bg-white/6">
          <span className="grid size-8 place-items-center rounded-full bg-[#202327] text-[11px] font-semibold text-white">CC</span>
          <span className="hidden text-left md:block">
            <span className="block text-xs font-medium text-white">Commandeur</span>
            <span className="block text-[10px] text-[#858b91]">Consulting</span>
          </span>
        </button>
        <Button variant="ghost" size="icon" aria-label="Abmelden" onClick={handleLogout}><LogOut size={17} /></Button>
      </div>
    </header>
  );
}
