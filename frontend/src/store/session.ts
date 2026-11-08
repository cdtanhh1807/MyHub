import { create } from 'zustand';
import type { User, Preferences, DriveFile } from '../types';

interface State {
  token: string | null; user: User | null; ready: boolean; workspace: DriveFile | null;
  preferences: Preferences; collapsed: boolean;
  set: (values: Partial<Omit<State, 'set'>>) => void;
}
// Access token chỉ nằm trong RAM; chỉ theme/ngôn ngữ không bí mật được lưu browser.
export const useSession = create<State>((set) => ({
  token: null, user: null, ready: false, workspace: null, collapsed: localStorage.getItem('myhub.collapsed') === 'true',
  preferences: {
    language: localStorage.getItem('myhub.language') === 'en' ? 'en' : 'vi',
    theme: (['light', 'dark', 'system'].includes(localStorage.getItem('myhub.theme') || '') ? localStorage.getItem('myhub.theme') : 'system') as Preferences['theme'],
    view: 'list', workspace_sort: 'name', direction: 'asc',
  },
  set: (values) => set(values),
}));

// Chỉ lưu trạng thái Panel trên browser hiện tại; token và thông tin phiên vẫn nằm trong RAM.
useSession.subscribe((state, previous) => {
  if (state.collapsed !== previous.collapsed) localStorage.setItem('myhub.collapsed', String(state.collapsed));
});
