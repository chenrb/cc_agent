import { client } from './client';
import type { AuthUser, LoginResponse, UserRole } from './types';

export const authApi = {
	/** `silent`: the login form and auth guard render their own inline errors. */
	login: (username: string, password: string) =>
		client.post<LoginResponse>(
			'/auth/login',
			{ username, password },
			undefined,
			{ silent: true },
		),
	/** `silent`: refresh is an automatic retry; a failure falls through to logout. */
	refresh: () =>
		client.post<{ expires_in: number }>(
			'/auth/refresh',
			undefined,
			undefined,
			{ silent: true },
		),
	logout: () => client.post<void>('/auth/logout'),
	/** `silent`: RequireAuth reacts without spamming toasts on a logged-out session. */
	me: () => client.get<AuthUser>('/auth/me', undefined, { silent: true }),
};

/** Body of `PATCH /admin/users/{id}`. Omitted fields are left unchanged. */
export interface UpdateUserBody {
	is_active?: boolean;
	role?: UserRole;
	password?: string;
}

export const adminUsersApi = {
	list: () => client.get<AuthUser[]>('/admin/users'),
	create: (username: string, password: string, role: UserRole) =>
		client.post<Pick<AuthUser, 'id' | 'username' | 'role'>>(
			'/admin/users',
			{ username, password, role },
		),
	update: (id: number, body: UpdateUserBody) =>
		client.patch<Pick<AuthUser, 'id' | 'username' | 'role' | 'is_active'>>(
			`/admin/users/${id}`,
			body,
		),
	remove: (id: number) => client.delete<void>(`/admin/users/${id}`),
};
