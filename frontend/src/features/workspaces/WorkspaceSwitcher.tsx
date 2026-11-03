import { Boxes } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Dropdown } from '../../components/Select';
import type { DriveFile } from '../../types';

// Bộ chọn trên Panel mở danh sách Workspace hiện có và đi thẳng vào thư mục của lựa chọn.
export function WorkspaceSwitcher({ workspaces, selected, onSelect }: { workspaces: DriveFile[]; selected: DriveFile | null; onSelect: (workspace: DriveFile) => void }) {
  const { t } = useTranslation();
  return <Dropdown className="workspace-switcher" aria-label={t('chooseWorkspace')} value={selected?.id || ''} options={workspaces.map(workspace => ({ value: workspace.id, label: workspace.name }))} onValueChange={id => {
    // Tra ID trong dữ liệu Drive đã tải, không dùng tên để điều hướng hoặc tạo Workspace.
    const workspace = workspaces.find(item => item.id === id);
    if (workspace) onSelect(workspace);
  }} trigger={<><span className="switch-icon"><Boxes size={18} /></span><span><small>{t('workspace')}</small><strong>{selected?.name || t('chooseWorkspace')}</strong></span></>} />;
}
