import { Ban, ChevronDown, Keyboard, PlusCircle } from 'lucide-react';
import { useEffect, useState } from 'react';

import type { ChatModelConfig } from '@/api';
import { Button } from '@/components/ui/button';
import {
	Dialog,
	DialogContent,
	DialogDescription,
	DialogFooter,
	DialogHeader,
	DialogTitle,
} from '@/components/ui/dialog';
import {
	DropdownMenu,
	DropdownMenuContent,
	DropdownMenuGroup,
	DropdownMenuItem,
	DropdownMenuLabel,
	DropdownMenuSeparator,
	DropdownMenuSub,
	DropdownMenuSubContent,
	DropdownMenuSubTrigger,
	DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Field, FieldGroup, FieldLabel } from '@/components/ui/field.tsx';
import { Input } from '@/components/ui/input';
import {
	Select,
	SelectContent,
	SelectItem,
	SelectTrigger,
	SelectValue,
} from '@/components/ui/select';
import { useAvailableModels, type CredentialWithModels } from '@/hooks/useAvailableModels';
import { useTranslation } from '@/i18n/useI18n.ts';
import { cn } from '@/lib/utils';

interface Props extends Omit<React.ComponentPropsWithoutRef<typeof Button>, 'onChange' | 'value'> {
	value?: ChatModelConfig | null;
	/**
	 * Called when the user selects a model, or — when `allowClear` is true —
	 * clears the selection (in which case `null` is emitted).
	 */
	onChange?: (value: ChatModelConfig | null) => void;
	onAddCredential?: () => void;
	refetchTrigger?: number;
	/** Override the trigger label shown when no model is selected. */
	placeholder?: string;
	/**
	 * When true, append a "clear selection" item to the dropdown that emits
	 * `null` via `onChange`. Used by the fallback selector.
	 */
	allowClear?: boolean;
	/** Override the label of the "clear selection" item. */
	clearLabel?: string;
}

// ─── Custom model dialog ─────────────────────────────────────────────────────

/** One credential flattened across provider groups, keyed for the Select. */
interface CredentialOption {
	/** Composite `${type}:${credentialId}` used as the select value. */
	key: string;
	type: string;
	id: string;
	label: string;
}

function flattenCredentials(
	groups: Record<string, CredentialWithModels[]>,
): CredentialOption[] {
	return Object.entries(groups).flatMap(([type, items]) =>
		items.map(({ credential }) => ({
			key: `${type}:${credential.id}`,
			type,
			id: credential.id,
			label: `${type.replace(/_credential$/, '')} · ${(credential.data.name as string) || credential.id.slice(0, 8)}`,
		})),
	);
}

interface CustomModelDialogProps {
	open: boolean;
	onOpenChange: (open: boolean) => void;
	groups: Record<string, CredentialWithModels[]>;
	/** Preselected credential (`${type}:${id}`) when the dialog opens. */
	defaultKey?: string | null;
	onConfirm: (type: string, credentialId: string, model: string) => void;
}

/**
 * Type any model name on top of an existing credential — the backend's
 * `ChatModelConfig.model` is a free string, so relay / local / freshly
 * released models outside the built-in catalog work as-is once the name
 * can be entered here.
 */
function CustomModelDialog({
	open,
	onOpenChange,
	groups,
	defaultKey,
	onConfirm,
}: CustomModelDialogProps) {
	const { t } = useTranslation();
	const options = flattenCredentials(groups);
	const [selectedKey, setSelectedKey] = useState('');
	const [model, setModel] = useState('');

	// The dialog stays mounted (state survives close), so re-initialize on
	// every open: previous input must never leak into the next session.
	useEffect(() => {
		if (!open) return;
		setModel('');
		setSelectedKey((prev) => {
			if (options.some((o) => o.key === prev)) return prev;
			if (defaultKey && options.some((o) => o.key === defaultKey)) return defaultKey;
			return options[0]?.key ?? '';
		});
		// `options`/`defaultKey` are only read for initialization; listing
		// them would re-run mid-session. Groups are static while open.
		// eslint-disable-next-line react-hooks/exhaustive-deps
	}, [open]);

	const handleConfirm = () => {
		const opt = options.find((o) => o.key === selectedKey);
		const name = model.trim();
		if (!opt || !name) return;
		onConfirm(opt.type, opt.id, name);
		onOpenChange(false);
	};

	return (
		<Dialog open={open} onOpenChange={onOpenChange}>
			<DialogContent className="!w-[420px] !max-w-[420px]">
				<DialogHeader>
					<DialogTitle>{t('llm-select.custom.title')}</DialogTitle>
					<DialogDescription>{t('llm-select.custom.description')}</DialogDescription>
				</DialogHeader>
				<FieldGroup>
					<Field>
						<FieldLabel>{t('llm-select.custom.credential')}</FieldLabel>
						<Select value={selectedKey} onValueChange={setSelectedKey}>
							<SelectTrigger className="w-full">
								<SelectValue
									placeholder={t('llm-select.custom.credentialPlaceholder')}
								/>
							</SelectTrigger>
							<SelectContent>
								{options.map((o) => (
									<SelectItem key={o.key} value={o.key}>
										{o.label}
									</SelectItem>
								))}
							</SelectContent>
						</Select>
					</Field>
					<Field>
						<FieldLabel>{t('llm-select.custom.model')}</FieldLabel>
						<Input
							autoFocus
							value={model}
							onChange={(e) => setModel(e.target.value)}
							onKeyDown={(e) => {
								if (e.key === 'Enter') handleConfirm();
							}}
							placeholder={t('llm-select.custom.modelPlaceholder')}
						/>
					</Field>
				</FieldGroup>
				<DialogFooter>
					<Button variant="ghost" onClick={() => onOpenChange(false)}>
						{t('common.cancel')}
					</Button>
					<Button onClick={handleConfirm} disabled={!selectedKey || !model.trim()}>
						<Keyboard className="size-3.5" />
						{t('llm-select.custom.confirm')}
					</Button>
				</DialogFooter>
			</DialogContent>
		</Dialog>
	);
}

// ─── LlmSelect ────────────────────────────────────────────────────────────────

export function LlmSelect({
	value,
	onChange,
	onAddCredential,
	refetchTrigger,
	placeholder,
	allowClear = false,
	clearLabel,
	className,
	...props
}: Props) {
	const { groups, loading, refetch } = useAvailableModels();
	const { t } = useTranslation();
	const [customOpen, setCustomOpen] = useState(false);
	const hasOptions = Object.keys(groups).length > 0;

	useEffect(() => {
		if (refetchTrigger !== undefined && refetchTrigger > 0) refetch();
	}, [refetchTrigger, refetch]);

	const handleSelect = (type: string, credentialId: string, model: string) => {
		onChange?.({ type, credential_id: credentialId, model, parameters: {} });
	};

	const displayLabel = value?.model
		? value.model
		: loading
			? t('llm-select.loading')
			: (placeholder ?? t('llm-select.placeholder'));

	return (
		<>
			<DropdownMenu>
				<DropdownMenuTrigger asChild>
					<Button
						variant="outline"
						size="sm"
						className={cn('justify-between gap-1 font-normal', className)}
						{...props}
					>
						<span className="truncate">{displayLabel}</span>
						<ChevronDown className="size-3.5 text-muted-foreground" />
					</Button>
				</DropdownMenuTrigger>
				<DropdownMenuContent align="start" className="min-w-48 max-h-72 overflow-y-auto">
					{!loading && !hasOptions ? (
						<div className="px-2 py-3 text-center text-sm text-muted-foreground">
							<p className="font-medium">{t('llm-select.empty.title')}</p>
							<p className="text-xs mt-1">{t('llm-select.empty.description')}</p>
						</div>
					) : (
						Object.entries(groups).map(([type, items], idx) => {
							const isSingle = items.length === 1;
							return (
								<DropdownMenuGroup key={type}>
									{idx > 0 && <DropdownMenuSeparator />}
									<DropdownMenuLabel>
										{type.replace(/_credential$/, '')}
									</DropdownMenuLabel>
									{isSingle
										? items[0].models.map((m) => (
												<DropdownMenuItem
													key={m.name}
													onSelect={() =>
														handleSelect(
															type,
															items[0].credential.id,
															m.name,
														)
													}
												>
													{m.name}
												</DropdownMenuItem>
											))
										: items.map(({ credential, models }) => {
												const credName =
													(credential.data.name as string) ||
													credential.id.slice(0, 8);
												return (
													<DropdownMenuSub key={credential.id}>
														<DropdownMenuSubTrigger>
															{credName}
														</DropdownMenuSubTrigger>
														<DropdownMenuSubContent className="max-h-60 overflow-y-auto">
															{models.map((m) => (
																<DropdownMenuItem
																	key={m.name}
																	onSelect={() =>
																		handleSelect(
																			type,
																			credential.id,
																			m.name,
																		)
																	}
																>
																	{m.label}
																</DropdownMenuItem>
															))}
														</DropdownMenuSubContent>
													</DropdownMenuSub>
												);
											})}
								</DropdownMenuGroup>
							);
						})
					)}
					<DropdownMenuSeparator />
					<DropdownMenuItem
						disabled={loading || !hasOptions}
						onSelect={() => setCustomOpen(true)}
					>
						<Keyboard className="size-4" />
						<span>{t('llm-select.custom.menuItem')}</span>
					</DropdownMenuItem>
					{allowClear && (
						<DropdownMenuItem onSelect={() => onChange?.(null)} disabled={!value}>
							<Ban className="size-4" />
							<span>{clearLabel ?? t('llm-select.clear')}</span>
						</DropdownMenuItem>
					)}
					<DropdownMenuItem onSelect={onAddCredential}>
						<PlusCircle className="size-4" />
						<span>{t('llm-select.addCredential')}</span>
					</DropdownMenuItem>
				</DropdownMenuContent>
			</DropdownMenu>
			<CustomModelDialog
				open={customOpen}
				onOpenChange={setCustomOpen}
				groups={groups}
				defaultKey={value ? `${value.type}:${value.credential_id}` : null}
				onConfirm={handleSelect}
			/>
		</>
	);
}
