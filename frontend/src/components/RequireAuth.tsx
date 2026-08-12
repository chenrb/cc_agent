import { Loader2 } from 'lucide-react';
import { useEffect, useState } from 'react';
import type { ReactNode } from 'react';
import { Navigate, useLocation } from 'react-router-dom';

import { authApi } from '@/api/auth';

type State = 'loading' | 'ok' | 'out';

/**
 * Guards authenticated routes. A `GET /auth/me` on mount verifies the access
 * cookie; on success the role hint is refreshed so {@link RequireAdmin} can
 * decide synchronously without a flash of the wrong page. A failure routes to
 * `/login`, preserving where the user was headed.
 */
export function RequireAuth({ children }: { children: ReactNode }) {
	const [state, setState] = useState<State>('loading');
	const loc = useLocation();

	useEffect(() => {
		let alive = true;
		authApi
			.me()
			.then((user) => {
				if (!alive) return;
				localStorage.setItem('username', user.username);
				localStorage.setItem('user_role', user.role);
				setState('ok');
			})
			.catch(() => {
				if (alive) setState('out');
			});
		return () => {
			alive = false;
		};
	}, []);

	if (state === 'loading') {
		return (
			<div className="flex items-center justify-center h-screen">
				<Loader2 className="size-6 animate-spin text-muted-foreground" />
			</div>
		);
	}
	if (state === 'out') {
		return <Navigate to="/login" replace state={{ from: loc.pathname }} />;
	}
	return <>{children}</>;
}
