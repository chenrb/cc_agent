import type { CredentialSchema, CredentialSchemaProperty } from '@/api';
import type { SchemaFormValue } from '@/components/form/SchemaForm';

function acceptsNull(prop: CredentialSchemaProperty): boolean {
	return prop.type === 'null' || (prop.anyOf ?? []).some((variant) => variant.type === 'null');
}

function shouldSkipField(key: string, prop: CredentialSchemaProperty): boolean {
	return key === 'id' || key === 'type' || prop.const !== undefined;
}

export function buildCredentialUpdateData(
	currentData: Record<string, unknown>,
	schema: CredentialSchema,
	values: Record<string, SchemaFormValue>,
): Record<string, unknown> {
	const data: Record<string, unknown> = { ...currentData };
	const required = new Set(schema.required ?? []);

	for (const [key, prop] of Object.entries(schema.properties)) {
		if (shouldSkipField(key, prop)) continue;

		const value = values[key];
		if (value === undefined || value === '') {
			if (prop.writeOnly) continue;
			if (acceptsNull(prop)) {
				data[key] = null;
			} else if (!required.has(key)) {
				delete data[key];
			}
			continue;
		}

		data[key] = value;
	}

	return data;
}
