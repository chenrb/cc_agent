import { client } from './client';
import type { HealthResponse } from './types';

/** The probe is I/O-free on the server, so anything this slow is a stalled backend. */
const HEALTH_TIMEOUT_MS = 10_000;

export const healthApi = {
	/**
	 * Probe a backend before its address is persisted — the base URL is passed
	 * explicitly rather than read from localStorage. `/health` is a public
	 * sentinel on the auth gateway, so no credentials are needed.
	 */
	check: (baseUrl: string) =>
		client.get<HealthResponse>('/health', undefined, {
			silent: true,
			baseUrl,
			timeoutMs: HEALTH_TIMEOUT_MS,
		}),
};
