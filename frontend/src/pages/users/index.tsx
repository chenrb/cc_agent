import { KeyRound, Loader2, Trash2, UserPlus } from 'lucide-react';
import { useEffect, useState } from 'react';
import type { FormEvent } from 'react';

import { adminUsersApi } from '@/api/auth';
import type { AuthUser, UserRole } from '@/api/types';
import { DeleteDialog } from '@/components/dialog/DeleteDialog';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
	Dialog,
	DialogContent,
	DialogDescription,
	DialogFooter,
	DialogHeader,
	DialogTitle,
} from '@/components/ui/dialog';
import { Field, FieldGroup, FieldLabel } from '@/components/ui/field';
import { Input } from '@/components/ui/input';
import {
	Select,
	SelectContent,
	SelectItem,
	SelectTrigger,
	SelectValue,
} from '@/components/ui/select';
import { useTranslation } from '@/i18n/useI18n';

export const UsersPage = () => {
	const { t } = useTranslation();
	const [users, setUsers] = useState<AuthUser[]>([]);
	const [loading, setLoading] = useState(true);
	const [createOpen, setCreateOpen] = useState(false);
	const [deleteTarget, setDeleteTarget] = useState<AuthUser | null>(null);
	const [resetTarget, setResetTarget] = useState<AuthUser | null>(null);

	const load = async () => {
		try {
			setUsers(await adminUsersApi.list());
		} catch {
			// The client surfaces the error via toast; nothing to render here.
		} finally {
			setLoading(false);
		}
	};
	useEffect(() => {
		void load();
	}, []);

	const toggleActive = async (u: AuthUser) => {
		try {
			await adminUsersApi.update(u.id, { is_active: !u.is_active });
			await load();
		} catch {
			/* toasted by client */
		}
	};

	const remove = async () => {
		if (!deleteTarget) return;
		try {
			await adminUsersApi.remove(deleteTarget.id);
			setDeleteTarget(null);
			await load();
		} catch {
			/* toasted by client */
		}
	};

	return (
		<div className="p-6 mx-auto w-full max-w-4xl">
			<div className="flex items-center justify-between mb-4">
				<div>
					<h1 className="text-xl font-semibold">{t('users.title')}</h1>
					<p className="text-sm text-muted-foreground">{t('users.description')}</p>
				</div>
				<Button onClick={() => setCreateOpen(true)}>
					<UserPlus className="size-3.5" />
					{t('users.create')}
				</Button>
			</div>

			<div className="overflow-hidden rounded-lg border">
				<table className="w-full text-sm">
					<thead className="bg-muted/50">
						<tr>
							<th className="px-3 py-2 text-left font-medium">
								{t('users.username')}
							</th>
							<th className="px-3 py-2 text-left font-medium">{t('users.role')}</th>
							<th className="px-3 py-2 text-left font-medium">
								{t('users.status')}
							</th>
							<th className="px-3 py-2 text-right font-medium">
								{t('users.actions')}
							</th>
						</tr>
					</thead>
					<tbody>
						{loading ? (
							<tr>
								<td colSpan={4} className="py-8 text-center">
									<Loader2 className="inline size-4 animate-spin text-muted-foreground" />
								</td>
							</tr>
						) : users.length === 0 ? (
							<tr>
								<td colSpan={4} className="py-8 text-center text-muted-foreground">
									{t('common.noData')}
								</td>
							</tr>
						) : (
							users.map((u) => (
								<tr key={u.id} className="border-t">
									<td className="px-3 py-2 font-medium">{u.username}</td>
									<td className="px-3 py-2">
										<Badge variant={u.role === 'admin' ? 'default' : 'secondary'}>
											{u.role === 'admin'
												? t('users.roleAdmin')
												: t('users.roleUser')}
										</Badge>
									</td>
									<td className="px-3 py-2">
										<Badge variant={u.is_active ? 'outline' : 'destructive'}>
											{u.is_active ? t('users.active') : t('users.disabled')}
										</Badge>
									</td>
									<td className="px-3 py-2 text-right">
										<div className="inline-flex gap-2 whitespace-nowrap">
											<Button
												size="sm"
												variant="outline"
												onClick={() => toggleActive(u)}
											>
												{u.is_active ? t('users.disable') : t('users.enable')}
											</Button>
											<Button
												size="sm"
												variant="outline"
												onClick={() => setResetTarget(u)}
											>
												<KeyRound className="size-3.5" />
												{t('users.resetPassword')}
											</Button>
											<Button
												size="sm"
												variant="outline"
												onClick={() => setDeleteTarget(u)}
											>
												<Trash2 className="size-3.5" />
												{t('users.delete')}
											</Button>
										</div>
									</td>
								</tr>
							))
						)}
					</tbody>
				</table>
			</div>

			<CreateUserDialog
				open={createOpen}
				onOpenChange={setCreateOpen}
				onCreated={load}
			/>
			<DeleteDialog
				open={deleteTarget !== null}
				onOpenChange={(o) => !o && setDeleteTarget(null)}
				title={deleteTarget ? t('users.deleteTitle', { name: deleteTarget.username }) : ''}
				description={t('users.deleteDescription')}
				confirmLabel={t('users.delete')}
				onConfirm={remove}
			/>
			<ResetPasswordDialog
				target={resetTarget}
				onOpenChange={(o) => !o && setResetTarget(null)}
				onDone={load}
			/>
		</div>
	);
};

function CreateUserDialog({
	open,
	onOpenChange,
	onCreated,
}: {
	open: boolean;
	onOpenChange: (open: boolean) => void;
	onCreated: () => void;
}) {
	const { t } = useTranslation();
	const [username, setUsername] = useState('');
	const [password, setPassword] = useState('');
	const [role, setRole] = useState<UserRole>('user');
	const [busy, setBusy] = useState(false);

	useEffect(() => {
		if (!open) {
			setUsername('');
			setPassword('');
			setRole('user');
			setBusy(false);
		}
	}, [open]);

	const submit = async (e: FormEvent) => {
		e.preventDefault();
		setBusy(true);
		try {
			await adminUsersApi.create(username.trim(), password, role);
			onOpenChange(false);
			onCreated();
		} catch {
			/* conflict / validation errors are toasted by the client */
		} finally {
			setBusy(false);
		}
	};

	return (
		<Dialog open={open} onOpenChange={onOpenChange}>
			<DialogContent className="max-w-sm">
				<DialogHeader>
					<DialogTitle>{t('users.createUser')}</DialogTitle>
				</DialogHeader>
				<form onSubmit={submit}>
					<FieldGroup>
						<Field>
							<FieldLabel>{t('users.username')}</FieldLabel>
							<Input
								value={username}
								onChange={(e) => setUsername(e.target.value)}
								required
								autoFocus
							/>
						</Field>
						<Field>
							<FieldLabel>{t('users.password')}</FieldLabel>
							<Input
								type="password"
								value={password}
								onChange={(e) => setPassword(e.target.value)}
								required
							/>
						</Field>
						<Field>
							<FieldLabel>{t('users.role')}</FieldLabel>
							<Select value={role} onValueChange={(v) => setRole(v as UserRole)}>
								<SelectTrigger className="w-full">
									<SelectValue />
								</SelectTrigger>
								<SelectContent>
									<SelectItem value="user">{t('users.roleUser')}</SelectItem>
									<SelectItem value="admin">{t('users.roleAdmin')}</SelectItem>
								</SelectContent>
							</Select>
						</Field>
						<DialogFooter>
							<Button
								type="button"
								variant="ghost"
								onClick={() => onOpenChange(false)}
								disabled={busy}
							>
								{t('common.cancel')}
							</Button>
							<Button type="submit" disabled={busy}>
								{busy && <Loader2 className="size-3.5 animate-spin" />}
								{t('users.save')}
							</Button>
						</DialogFooter>
					</FieldGroup>
				</form>
			</DialogContent>
		</Dialog>
	);
}

function ResetPasswordDialog({
	target,
	onOpenChange,
	onDone,
}: {
	target: AuthUser | null;
	onOpenChange: (open: boolean) => void;
	onDone: () => void;
}) {
	const { t } = useTranslation();
	const [password, setPassword] = useState('');
	const [busy, setBusy] = useState(false);

	useEffect(() => {
		if (!target) {
			setPassword('');
			setBusy(false);
		}
	}, [target]);

	const submit = async (e: FormEvent) => {
		e.preventDefault();
		if (!target) return;
		setBusy(true);
		try {
			await adminUsersApi.update(target.id, { password });
			onOpenChange(false);
			onDone();
		} catch {
			/* toasted by client */
		} finally {
			setBusy(false);
		}
	};

	return (
		<Dialog open={target !== null} onOpenChange={onOpenChange}>
			<DialogContent className="max-w-sm">
				<DialogHeader>
					<DialogTitle>{t('users.resetPassword')}</DialogTitle>
					{target && <DialogDescription>{target.username}</DialogDescription>}
				</DialogHeader>
				<form onSubmit={submit}>
					<FieldGroup>
						<Field>
							<FieldLabel>{t('users.newPassword')}</FieldLabel>
							<Input
								type="password"
								value={password}
								onChange={(e) => setPassword(e.target.value)}
								required
								autoFocus
							/>
						</Field>
						<DialogFooter>
							<Button
								type="button"
								variant="ghost"
								onClick={() => onOpenChange(false)}
								disabled={busy}
							>
								{t('common.cancel')}
							</Button>
							<Button type="submit" disabled={busy}>
								{busy && <Loader2 className="size-3.5 animate-spin" />}
								{t('users.save')}
							</Button>
						</DialogFooter>
					</FieldGroup>
				</form>
			</DialogContent>
		</Dialog>
	);
}
