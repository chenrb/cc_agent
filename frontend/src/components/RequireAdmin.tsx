import type { ReactNode } from 'react';
import { Navigate } from 'react-router-dom';

/**
 * Gates admin-only routes using the role hint that {@link RequireAuth}
 * refreshed on mount. Non-admins are redirected to chat rather than shown an
 * error page.
 */
export function RequireAdmin({ children }: { children: ReactNode }) {
	const role = localStorage.getItem('user_role');
	if (role !== 'admin') {
		return <Navigate to="/chat" replace />;
	}
	return <>{children}</>;
}
