import { useTranslation } from '@/i18n/useI18n';

/** Placeholder — the full management UI arrives in the next task. */
export const UsersPage = () => {
	const { t } = useTranslation();
	return (
		<div className="p-6">
			<h1 className="text-xl">{t('users.title')}</h1>
		</div>
	);
};
