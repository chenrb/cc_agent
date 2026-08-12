import { CircleAlert, Loader2 } from 'lucide-react';
import { useState } from 'react';
import type { FormEvent } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';

import { authApi } from '@/api/auth';
import { ApiError } from '@/api/client';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import {
	Card,
	CardContent,
	CardDescription,
	CardHeader,
	CardTitle,
} from '@/components/ui/card';
import { Field, FieldGroup, FieldLabel } from '@/components/ui/field';
import { Input } from '@/components/ui/input';
import { useTranslation } from '@/i18n/useI18n';

export const LoginPage = () => {
	const { t } = useTranslation();
	const nav = useNavigate();
	const loc = useLocation() as { state?: { from?: string } | null };
	const [username, setUsername] = useState('');
	const [password, setPassword] = useState('');
	const [errorMsg, setErrorMsg] = useState('');
	const [busy, setBusy] = useState(false);

	const submit = async (e: FormEvent) => {
		e.preventDefault();
		setBusy(true);
		setErrorMsg('');
		try {
			const { user } = await authApi.login(username.trim(), password);
			// Identity is carried by the cookie; these are UI hints only
			// (RequireAdmin reads the role synchronously).
			localStorage.setItem('username', user.username);
			localStorage.setItem('user_role', user.role);
			const target = loc.state?.from || '/chat';
			nav(target, { replace: true });
		} catch (err) {
			setErrorMsg(err instanceof ApiError ? err.detail : t('login.errorGeneric'));
		} finally {
			setBusy(false);
		}
	};

	return (
		<div className="flex items-center justify-center h-screen">
			<Card className="w-full max-w-sm">
				<CardHeader>
					<CardTitle>{t('login.title')}</CardTitle>
					<CardDescription>{t('login.description')}</CardDescription>
				</CardHeader>
				<CardContent>
					<form onSubmit={submit}>
						<FieldGroup>
							<Field>
								<FieldLabel htmlFor="login-username">
									{t('login.username')}
								</FieldLabel>
								<Input
									id="login-username"
									value={username}
									onChange={(e) => setUsername(e.target.value)}
									autoFocus
									required
								/>
							</Field>
							<Field>
								<FieldLabel htmlFor="login-password">
									{t('login.password')}
								</FieldLabel>
								<Input
									id="login-password"
									type="password"
									value={password}
									onChange={(e) => setPassword(e.target.value)}
									required
								/>
							</Field>
							{errorMsg && (
								<Alert variant="destructive">
									<CircleAlert />
									<AlertDescription>{errorMsg}</AlertDescription>
								</Alert>
							)}
							<Field>
								<Button type="submit" className="w-full" disabled={busy}>
									{busy && <Loader2 className="size-3.5 animate-spin" />}
									{busy ? t('login.signingIn') : t('login.submit')}
								</Button>
							</Field>
						</FieldGroup>
					</form>
				</CardContent>
			</Card>
		</div>
	);
};
