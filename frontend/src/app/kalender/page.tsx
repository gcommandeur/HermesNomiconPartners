"use client";

import { useMemo, useState } from "react";
import { ChevronLeft, ChevronRight, Plus } from "lucide-react";
import { PageHeader } from "@/components/crm/page-header";
import { ErrorState } from "@/components/crm/error-state";
import { CalendarView, EVENT_TYPE_LABEL } from "@/components/crm/calendar-view";
import { CalendarEventModal } from "@/components/crm/calendar-event-modal";
import { Button } from "@/components/ui/button";
import {
  useAdminUsersCache,
  useCalendarEventsCache,
  useCurrentUser,
  invalidateCalendarEventsCache,
} from "@/lib/api/hooks";
import {
  addDays,
  endOfMonthGrid,
  formatMonthLabel,
  startOfMonthGrid,
  startOfWeek,
  toLocalIsoString,
} from "@/lib/calendar-utils";
import type { CalendarEvent } from "@/lib/api/types";

type ViewMode = "month" | "week";
type OwnerFilter = "me" | "all" | string;

const selectClass = "h-9 rounded-md border border-white/10 bg-[#0D1B2E] px-2 text-xs text-[#F8FAFC] outline-none focus:border-[#1F5FA8]";

export default function CalendarPage() {
  const { data: userData, isLoading: userLoading, error: userError } = useCurrentUser();
  const currentUser = userData?.data;
  const isAdmin = currentUser?.is_admin ?? false;

  const [view, setView] = useState<ViewMode>("month");
  const [currentDate, setCurrentDate] = useState(() => new Date());
  const [ownerFilter, setOwnerFilter] = useState<OwnerFilter>("me");
  const [modalState, setModalState] = useState<{ open: boolean; event: CalendarEvent | null; defaultStart?: string }>({
    open: false,
    event: null,
  });

  const { data: adminUsersData } = useAdminUsersCache(isAdmin);
  const adminUsers = useMemo(() => adminUsersData?.data ?? [], [adminUsersData]);

  const range = useMemo(() => {
    if (view === "week") {
      const start = startOfWeek(currentDate);
      return { start, end: addDays(start, 6) };
    }
    return { start: startOfMonthGrid(currentDate), end: endOfMonthGrid(currentDate) };
  }, [view, currentDate]);

  const ownerUserId =
    !isAdmin || ownerFilter === "all" ? undefined : ownerFilter === "me" ? currentUser?.id : ownerFilter;

  const {
    data: eventsData,
    isLoading: eventsLoading,
    error: eventsError,
    mutate: retryEvents,
  } = useCalendarEventsCache({
    startFrom: toLocalIsoString(range.start),
    startTo: toLocalIsoString(range.end),
    ownerUserId,
  });
  const events = eventsData?.data ?? [];

  function navigate(direction: -1 | 1) {
    setCurrentDate((current) => addDays(current, direction * (view === "week" ? 7 : 30)));
  }

  function openCreateModal(day?: Date) {
    setModalState({
      open: true,
      event: null,
      defaultStart: day ? `${toLocalIsoString(day).slice(0, 10)}T09:00` : undefined,
    });
  }

  function openEditModal(event: CalendarEvent) {
    setModalState({ open: true, event });
  }

  function closeModal() {
    setModalState({ open: false, event: null });
  }

  async function handleSaved() {
    closeModal();
    await invalidateCalendarEventsCache();
  }

  async function handleDeleted() {
    closeModal();
    await invalidateCalendarEventsCache();
  }

  if (userError || eventsError) {
    return <ErrorState onRetry={() => { void retryEvents(); }} />;
  }

  if (userLoading || !currentUser) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 6 }).map((_, index) => (
          <div key={index} className="h-14 animate-pulse rounded-lg bg-[#0D1B2E]" />
        ))}
      </div>
    );
  }

  return (
    <>
      <PageHeader
        eyebrow="Termine"
        title="Kalender"
        action={
          <Button onClick={() => openCreateModal()}>
            <Plus size={15} />Termin anlegen
          </Button>
        }
      />

      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Button size="sm" variant="outline" onClick={() => navigate(-1)} aria-label="Zurück">
            <ChevronLeft size={14} />
          </Button>
          <Button size="sm" variant="outline" onClick={() => setCurrentDate(new Date())}>Heute</Button>
          <Button size="sm" variant="outline" onClick={() => navigate(1)} aria-label="Weiter">
            <ChevronRight size={14} />
          </Button>
          <span className="ml-2 text-sm font-semibold text-[#F8FAFC]">{formatMonthLabel(currentDate)}</span>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {isAdmin && (
            <select
              className={selectClass}
              value={ownerFilter}
              onChange={(e) => setOwnerFilter(e.target.value)}
            >
              <option value="me">Meine Termine</option>
              <option value="all">Alle Termine</option>
              {adminUsers.map((user) => (
                <option key={user.id} value={user.id}>
                  {user.display_name ?? user.email}
                </option>
              ))}
            </select>
          )}
          <div className="flex rounded-lg border border-white/10 bg-[#0D1B2E] p-1 text-xs">
            <button
              className={`rounded-md px-3 py-1.5 ${view === "month" ? "bg-[#153A66] text-white" : "text-[#94A3B8]"}`}
              onClick={() => setView("month")}
            >
              Monat
            </button>
            <button
              className={`rounded-md px-3 py-1.5 ${view === "week" ? "bg-[#153A66] text-white" : "text-[#94A3B8]"}`}
              onClick={() => setView("week")}
            >
              Woche
            </button>
          </div>
        </div>
      </div>

      <div className="mb-4 flex gap-3 text-[11px] text-[#94A3B8]">
        {(Object.entries(EVENT_TYPE_LABEL) as [keyof typeof EVENT_TYPE_LABEL, string][]).map(([key, label]) => (
          <span key={key} className="flex items-center gap-1.5">
            <span
              className={`size-2 rounded-full ${
                key === "interview" ? "bg-[#1F5FA8]" : key === "quali_call" ? "bg-[#4f8a68]" : "bg-[#8a9095]"
              }`}
            />
            {label}
          </span>
        ))}
      </div>

      {eventsLoading ? (
        <div className="space-y-2">
          {Array.from({ length: 6 }).map((_, index) => (
            <div key={index} className="h-20 animate-pulse rounded-lg bg-[#0D1B2E]" />
          ))}
        </div>
      ) : (
        <CalendarView
          view={view}
          currentDate={currentDate}
          events={events}
          onDayClick={openCreateModal}
          onEventClick={openEditModal}
        />
      )}

      {modalState.open && (
        <CalendarEventModal
          event={modalState.event}
          defaultStart={modalState.defaultStart}
          currentUserId={currentUser.id}
          isAdmin={isAdmin}
          adminUsers={adminUsers}
          onClose={closeModal}
          onSaved={handleSaved}
          onDeleted={handleDeleted}
        />
      )}
    </>
  );
}
