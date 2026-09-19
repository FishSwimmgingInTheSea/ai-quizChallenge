import { create } from 'zustand'
import { UserProfile } from '../types'

/**
 * 用户登录态 + 当前资料（用户系统方案设计 §10.4）。
 * Token 本体存于 storage（services/token.ts），store 只维护展示态。
 */
export interface UserState {
  profile: UserProfile | null
  isLoggedIn: boolean

  setAuth: (profile: UserProfile) => void
  setProfile: (profile: UserProfile) => void
  setTotalXp: (totalXp: number) => void
  clear: () => void
}

export const useUserStore = create<UserState>((set) => ({
  profile: null,
  isLoggedIn: false,

  setAuth: (profile) => set({ profile, isLoggedIn: true }),

  setProfile: (profile) => set({ profile }),

  setTotalXp: (totalXp) =>
    set((s) =>
      s.profile ? { profile: { ...s.profile, total_xp: totalXp } } : {},
    ),

  clear: () => set({ profile: null, isLoggedIn: false }),
}))
