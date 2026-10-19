"use client";

// NOMICON: Glocke - offene, fällige Aufgaben der angemeldeten Person als Meldungen (vorhandene
// Aufgaben aus dem Tagesjob, kein neuer Kanal). Aktualisiert sich jede Minute.
import useSWR from "swr";
import { apiGet } from "./client";
import type { Task } from "./types";
import { useCurrentUser } from "./hooks";
import { notificationItems, type NotificationItem } from "@/lib/notifications";

async function getOpenTasks(ownerId: string): Promise<NotificationItem[]> {
  const result = await apiGet<Task[]>(`/tasks?status=open&owner_user_id=${ownerId}&limit=50`, []);
  return notificationItems(result.data);
}

export function useNotifications(): NotificationItem[] {
  const { data: me } = useCurrentUser();
  const ownerId = me?.data.id || null;
  const { data } = useSWR(ownerId ? `/tasks?notifications=${ownerId}` : null, () => getOpenTasks(ownerId as string), {
    refreshInterval: 60_000,
    revalidateOnFocus: true,
    dedupingInterval: 10_000,
  });
  return data ?? [];
}
