"use client";

import { AlertCircle } from "lucide-react";
import { Button } from "@/components/ui/button";

export default function ErrorPage({ reset }: { reset: () => void }) {
  return <div className="grid min-h-[60vh] place-items-center text-center"><div><AlertCircle className="mx-auto text-[#173f77]" /><h1 className="mt-4 text-xl font-semibold">Die Ansicht konnte nicht geladen werden.</h1><p className="mt-2 text-sm text-[#747a80]">Bitte versuchen Sie es erneut. Die Daten wurden nicht verändert.</p><Button className="mt-5" onClick={reset}>Erneut versuchen</Button></div></div>;
}
