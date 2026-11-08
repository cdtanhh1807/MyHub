import { useEffect } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { useSession } from '../store/session';
import { api } from '../services/api';
import type { Preferences } from '../types';
import { deviceId } from '../services/device';

// Cài đặt Mongo được phân vùng theo browser; các thiết bị không ghi đè theme/ngôn ngữ của nhau.
export function usePreferences() {
  const { user, preferences, set } = useSession();
  const { i18n } = useTranslation();
  const client = useQueryClient();
  const query = useQuery({ queryKey: ['settings', user?.id, deviceId], enabled: !!user, queryFn: async () => (await api.get('/settings')).data.data as Preferences });
  useEffect(() => { if (query.data) set({ preferences: query.data }); }, [query.data, set]);
  useEffect(() => {
    void i18n.changeLanguage(preferences.language);
    document.documentElement.lang = preferences.language;
    localStorage.setItem('myhub.language', preferences.language);
    localStorage.setItem('myhub.theme', preferences.theme);
    const media = matchMedia('(prefers-color-scheme: dark)');
    const apply = () => document.documentElement.dataset.theme = preferences.theme === 'system' ? (media.matches ? 'dark' : 'light') : preferences.theme;
    apply(); media.addEventListener('change', apply); return () => media.removeEventListener('change', apply);
  }, [preferences.language, preferences.theme, i18n]);
  async function update(values: Partial<Preferences>) {
    // Lưu server thành công mới cập nhật store, tránh hiển thị đồng bộ giả khi API lỗi.
    const next = { ...useSession.getState().preferences, ...values };
    await api.put('/settings', next);
    set({ preferences: next });
    client.setQueryData(['settings', user?.id, deviceId], next);
    await client.invalidateQueries({ queryKey: ['workspaces'] });
  }
  return { preferences, update };
}
