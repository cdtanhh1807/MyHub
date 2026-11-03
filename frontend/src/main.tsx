import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import './i18n';
import './theme/app.css';
import App from './app/App';

// Không retry lỗi nghiệp vụ; chỉ thử lại một lần với lỗi kết nối hoặc server tạm thời.
const client = new QueryClient({ defaultOptions: { queries: { staleTime: 15000, retry: (count, error: unknown) => count < 1 && (!error || !(typeof error === 'object' && 'response' in error) || Number((error as { response?: { status: number } }).response?.status || 500) >= 500) } } });
createRoot(document.getElementById('root')!).render(<BrowserRouter><QueryClientProvider client={client}><App /></QueryClientProvider></BrowserRouter>);
