"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Briefcase, Building2, ChevronDown, Plus, Users } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Modal } from "@/components/ui/modal";
import { CandidateCreateForm } from "@/components/crm/candidate-create-modal";
import { ClientCreateForm } from "@/components/crm/client-create-modal";
import { SubmissionCreateForm } from "@/components/crm/submission-create-modal";

type Action = "candidate" | "client" | "submission" | null;

export function QuickActionMenu() {
  const router = useRouter();
  const [menuOpen, setMenuOpen] = useState(false);
  const [active, setActive] = useState<Action>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) setMenuOpen(false);
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  return (
    <div className="relative" ref={menuRef}>
      <Button size="sm" className="hidden sm:inline-flex" onClick={() => setMenuOpen((value) => !value)}>
        <Plus size={15} />Quick Action<ChevronDown size={14} />
      </Button>
      {menuOpen && (
        <div className="absolute right-0 top-11 z-50 w-56 rounded-lg border border-white/10 bg-brand-surface p-1.5 shadow-2xl">
          <button className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-sm text-brand-platinum hover:bg-white/8" onClick={() => { setActive("candidate"); setMenuOpen(false); }}>
            <Users size={15} />Kandidat anlegen
          </button>
          <button className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-sm text-brand-platinum hover:bg-white/8" onClick={() => { setActive("client"); setMenuOpen(false); }}>
            <Building2 size={15} />Kanzlei anlegen
          </button>
          <button className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-sm text-brand-platinum hover:bg-white/8" onClick={() => { setActive("submission"); setMenuOpen(false); }}>
            <Briefcase size={15} />Prozess erstellen
          </button>
        </div>
      )}

      {active === "candidate" && (
        <Modal title="Kandidat anlegen" eyebrow="Talent Pool" onClose={() => setActive(null)}>
          <CandidateCreateForm onDone={() => { setActive(null); router.refresh(); }} />
        </Modal>
      )}
      {active === "client" && (
        <Modal title="Kanzlei anlegen" eyebrow="Client Intelligence" onClose={() => setActive(null)}>
          <ClientCreateForm onDone={() => { setActive(null); router.refresh(); }} />
        </Modal>
      )}
      {active === "submission" && (
        <Modal
          title="Prozess erstellen"
          eyebrow="Recruiting-Prozesse"
          description="Ein Prozess beginnt bei Quali Call. Die Kanzlei kann optional sofort verknüpft oder erst ab Interview ergänzt werden."
          onClose={() => setActive(null)}
        >
          <SubmissionCreateForm onDone={() => { setActive(null); router.refresh(); }} />
        </Modal>
      )}
    </div>
  );
}
