import { Onborda, OnbordaProvider } from 'onborda';
import { useMemo, useState } from 'react';
import { createBrowserRouter, Navigate, RouterProvider, useNavigate } from 'react-router-dom';
import { Toaster } from 'sonner';

import { MCPHubPage } from './pages/mcp';
import { SkillHubPage } from './pages/skill';
import { RouteError } from '@/components/error/RouteError';
import { AppLayout } from '@/components/layout/AppLayout';
import { RequireAdmin } from '@/components/RequireAdmin';
import { RequireAuth } from '@/components/RequireAuth';
import { buildChatTour } from '@/components/tour/chatTourSteps';
import { TourCard } from '@/components/tour/TourCard';
import { UploadProvider } from '@/context/UploadContext';
import { useTranslation } from '@/i18n/useI18n';
import { ChannelPage } from '@/pages/channel';
import { ChatPage } from '@/pages/chat';
import { CredentialPage } from '@/pages/credential';
import { KnowledgePage } from '@/pages/knowledge';
import { LoginPage } from '@/pages/login';
import { SchedulePage } from '@/pages/schedule';
import { SetupPage } from '@/pages/setup';
import { UsersPage } from '@/pages/users';

function SetupPageRoute() {
	const navigate = useNavigate();
	return (
		<>
			<div className="h-screen">
				<SetupPage onComplete={() => navigate('/')} />
			</div>
			<Toaster richColors position="top-right" />
		</>
	);
}

const router = createBrowserRouter([
	{ path: '/login', element: <LoginPage />, errorElement: <RouteError /> },
	{
		// RequireAuth gates every authenticated route at the layout level: it
		// checks the access cookie once and bounces to /login on failure, so
		// each page below can assume a valid session.
		element: (
			<RequireAuth>
				<AppLayout />
			</RequireAuth>
		),
		errorElement: <RouteError />,
		children: [
			{
				// Content-level boundary: a crash in a page replaces only
				// the Outlet area, so AppLayout (the icon rail / nav) stays
				// usable. The parent route keeps its own errorElement as a
				// last-resort catch-all for AppLayout/AppSidebar crashes.
				errorElement: <RouteError />,
				children: [
					{ path: '/', element: <Navigate to="/chat" replace /> },
					{
						path: '/chat/:agentId?/:sessionId?/:memberId?',
						element: <ChatPage />,
					},
					{ path: '/schedule', element: <SchedulePage /> },
					{ path: '/channel', element: <ChannelPage /> },
					{ path: '/credential', element: <CredentialPage /> },
					{ path: '/mcp', element: <MCPHubPage /> },
					{ path: '/mcp/:hubId', element: <MCPHubPage /> },
					{ path: '/skill', element: <SkillHubPage /> },
					{ path: '/skill/:hubId', element: <SkillHubPage /> },
					{ path: '/knowledge', element: <KnowledgePage /> },
					{ path: '/knowledge/:kbId', element: <KnowledgePage /> },
					{
						path: '/users',
						element: (
							<RequireAdmin>
								<UsersPage />
							</RequireAdmin>
						),
					},
				],
			},
		],
	},
	{ path: '/setup', element: <SetupPageRoute />, errorElement: <RouteError /> },
]);

function App() {
	const { t } = useTranslation();
	const [setupComplete, setSetupComplete] = useState(() => !!localStorage.getItem('server_url'));
	const tours = useMemo(() => [buildChatTour(t)], [t]);

	if (!setupComplete) {
		return <SetupPage onComplete={() => setSetupComplete(true)} />;
	}

	return (
		<OnbordaProvider>
			<Onborda
				steps={tours}
				cardComponent={TourCard}
				shadowOpacity="0.6"
				cardTransition={{ type: 'spring', duration: 0.4 }}
			>
				<UploadProvider>
					<RouterProvider router={router} />
				</UploadProvider>
				<Toaster richColors position="top-right" />
			</Onborda>
		</OnbordaProvider>
	);
}

export default App;
