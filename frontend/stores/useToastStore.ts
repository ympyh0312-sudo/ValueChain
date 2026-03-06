import { create } from "zustand";
import type { ToastData, ToastType } from "@/components/ui/Toast";

interface ToastState {
  toasts: ToastData[];
  add:    (type: ToastType, title: string, message?: string) => void;
  remove: (id: string) => void;
}

export const useToastStore = create<ToastState>((set) => ({
  toasts: [],

  add: (type, title, message) =>
    set((s) => ({
      toasts: [
        ...s.toasts,
        { id: `${Date.now()}-${Math.random()}`, type, title, message },
      ],
    })),

  remove: (id) =>
    set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),
}));

// 편의 함수
export const toast = {
  success: (title: string, message?: string) =>
    useToastStore.getState().add("success", title, message),
  warning: (title: string, message?: string) =>
    useToastStore.getState().add("warning", title, message),
  error:   (title: string, message?: string) =>
    useToastStore.getState().add("error",   title, message),
};
