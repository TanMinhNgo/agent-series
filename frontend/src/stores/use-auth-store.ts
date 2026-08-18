import { create } from 'zustand';

export type AuthUser = {
  id: string;
  email: string;
  displayName: string | null;
  role: string;
};

type AuthState = {
  user: AuthUser | null;
  checked: boolean;
  setSession: (user: AuthUser | null) => void;
  clearSession: () => void;
};

// Do not persist this store: the HTTP-only session cookie and /auth/me remain
// the source of truth on every page load.
export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  checked: false,
  setSession: (user) => set({ user, checked: true }),
  clearSession: () => set({ user: null, checked: true }),
}));
