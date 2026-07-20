"use client";

import { useMemo } from "react";
import { Plus } from "lucide-react";
import { cn } from "@/lib/utils";
import {
  addDays,
  dateKey,
  dateKeyFromIso,
  endOfMonthGrid,
  formatDayLabel,
  formatTimeFromIso,
  formatWeekdayLabel,
  startOfMonthGrid,
  startOfWeek,
} from "@/lib/calendar-utils";
import type { CalendarEvent, CalendarEventType } from "@/lib/api/types";

const WEEKDAY_LABELS = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"];

const EVENT_TYPE_COLOR: Record<CalendarEventType, string> = {
  interview: "border-[#1F5FA8]/40 bg-[#153A66]/50 text-[#c5dcfa]",
  quali_call: "border-[#4f8a68]/35 bg-[#244d38]/50 text-[#a9d6b8]",
  other: "border-white/10 bg-white/8 text-[#CBD5E1]",
};

export const EVENT_TYPE_LABEL: Record<CalendarEventType, string> = {
  interview: "Interview",
  quali_call: "Quali Call",
  other: "Sonstiges",
};

function groupByDay(events: CalendarEvent[]): Map<string, CalendarEvent[]> {
  const map = new Map<string, CalendarEvent[]>();
  for (const event of events) {
    const key = dateKeyFromIso(event.start_at);
    const list = map.get(key) ?? [];
    list.push(event);
    map.set(key, list);
  }
  for (const list of map.values()) list.sort((a, b) => a.start_at.localeCompare(b.start_at));
  return map;
}

function EventChip({ event, onClick, compact }: { event: CalendarEvent; onClick: () => void; compact?: boolean }) {
  return (
    <button
      type="button"
      onClick={(clickEvent) => {
        clickEvent.stopPropagation();
        onClick();
      }}
      className={cn(
        "block w-full truncate rounded border px-1.5 py-0.5 text-left text-[11px] hover:brightness-110",
        EVENT_TYPE_COLOR[event.event_type],
        compact ? "mt-0.5" : "mt-1",
      )}
      title={event.title}
    >
      <span className="font-medium">{formatTimeFromIso(event.start_at)}</span> {event.title}
    </button>
  );
}

export function CalendarView({
  view,
  currentDate,
  events,
  onDayClick,
  onEventClick,
}: {
  view: "month" | "week";
  currentDate: Date;
  events: CalendarEvent[];
  onDayClick: (date: Date) => void;
  onEventClick: (event: CalendarEvent) => void;
}) {
  const eventsByDay = useMemo(() => groupByDay(events), [events]);

  const days = useMemo(() => {
    if (view === "week") {
      const start = startOfWeek(currentDate);
      return Array.from({ length: 7 }, (_, index) => addDays(start, index));
    }
    const start = startOfMonthGrid(currentDate);
    const end = endOfMonthGrid(currentDate);
    const count = Math.round((end.getTime() - start.getTime()) / (24 * 60 * 60 * 1000)) + 1;
    return Array.from({ length: count }, (_, index) => addDays(start, index));
  }, [view, currentDate]);

  const today = new Date();

  if (view === "week") {
    return (
      <div className="grid grid-cols-7 gap-2">
        {days.map((day) => {
          const dayEvents = eventsByDay.get(dateKey(day)) ?? [];
          const isToday = day.toDateString() === today.toDateString();
          return (
            <div
              key={dateKey(day)}
              className={cn(
                "min-h-[220px] rounded-lg border p-2",
                isToday ? "border-[#1F5FA8]/50 bg-[#102A4C]/40" : "border-white/10 bg-[#0D1B2E]/60",
              )}
            >
              <button
                type="button"
                onClick={() => onDayClick(day)}
                className="mb-2 flex w-full items-center justify-between text-xs text-[#94A3B8] hover:text-white"
              >
                <span>{formatWeekdayLabel(day)} {formatDayLabel(day)}</span>
                <Plus size={12} />
              </button>
              <div className="space-y-1">
                {dayEvents.map((event) => (
                  <EventChip key={event.id} event={event} onClick={() => onEventClick(event)} />
                ))}
              </div>
            </div>
          );
        })}
      </div>
    );
  }

  return (
    <div className="grid grid-cols-7 gap-2">
      {WEEKDAY_LABELS.map((label) => (
        <div key={label} className="pb-1 text-center text-[10px] uppercase tracking-wider text-[#8a9095]">
          {label}
        </div>
      ))}
      {days.map((day) => {
        const dayEvents = eventsByDay.get(dateKey(day)) ?? [];
        const inMonth = day.getMonth() === currentDate.getMonth();
        const isToday = day.toDateString() === today.toDateString();
        const visible = dayEvents.slice(0, 3);
        const overflow = dayEvents.length - visible.length;
        return (
          <button
            type="button"
            key={dateKey(day)}
            onClick={() => onDayClick(day)}
            className={cn(
              "min-h-[92px] rounded-lg border p-1.5 text-left align-top",
              inMonth ? "border-white/10 bg-[#0D1B2E]/60" : "border-white/5 bg-transparent opacity-50",
              isToday && "border-[#1F5FA8]/50 bg-[#102A4C]/40",
            )}
          >
            <span className="text-[11px] text-[#8a9095]">{day.getDate()}</span>
            {visible.map((event) => (
              <EventChip key={event.id} event={event} onClick={() => onEventClick(event)} compact />
            ))}
            {overflow > 0 && (
              <p className="mt-0.5 text-[10px] text-[#69A7EA]">+{overflow} mehr</p>
            )}
          </button>
        );
      })}
    </div>
  );
}
