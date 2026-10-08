import { RestrictedEventSettings } from "@/api";
import { z } from "zod";

export const OfflineFormSchema = z.object({
  offline_enabled: z.boolean(),
  offline_validity_minutes: z.number().int().min(1).max(1440),
  offline_sale_per_transaction: z.number().min(0).multipleOf(0.01),
  offline_sale_per_customer: z.number().min(0).multipleOf(0.01),
  offline_sale_per_till: z.number().min(0).multipleOf(0.01),
  offline_return_per_transaction: z.number().min(0).multipleOf(0.01),
  offline_return_per_customer: z.number().min(0).multipleOf(0.01),
  offline_return_per_till: z.number().min(0).multipleOf(0.01),
});

export type OfflineFormValues = z.infer<typeof OfflineFormSchema>;

export const offlineSettingDefaults = {
  offline_enabled: false,
  offline_validity_seconds: 7200,
  offline_sale_per_transaction_cents: 2000,
  offline_sale_per_customer_cents: 3000,
  offline_sale_per_till_cents: 50000,
  offline_return_per_transaction_cents: 2000,
  offline_return_per_customer_cents: 3000,
  offline_return_per_till_cents: 50000,
};

export const toEuros = (cents: number) => cents / 100;
const toCents = (euros: number) => Math.round(euros * 100);

export const toOfflineFormValues = (settings: RestrictedEventSettings): OfflineFormValues => ({
  offline_enabled: settings.offline_enabled ?? offlineSettingDefaults.offline_enabled,
  offline_validity_minutes: (settings.offline_validity_seconds ?? offlineSettingDefaults.offline_validity_seconds) / 60,
  offline_sale_per_transaction: toEuros(settings.offline_sale_per_transaction_cents ?? offlineSettingDefaults.offline_sale_per_transaction_cents),
  offline_sale_per_customer: toEuros(settings.offline_sale_per_customer_cents ?? offlineSettingDefaults.offline_sale_per_customer_cents),
  offline_sale_per_till: toEuros(settings.offline_sale_per_till_cents ?? offlineSettingDefaults.offline_sale_per_till_cents),
  offline_return_per_transaction: toEuros(settings.offline_return_per_transaction_cents ?? offlineSettingDefaults.offline_return_per_transaction_cents),
  offline_return_per_customer: toEuros(settings.offline_return_per_customer_cents ?? offlineSettingDefaults.offline_return_per_customer_cents),
  offline_return_per_till: toEuros(settings.offline_return_per_till_cents ?? offlineSettingDefaults.offline_return_per_till_cents),
});

export const toOfflineApiSettings = (values: OfflineFormValues) => ({
  offline_enabled: values.offline_enabled,
  offline_validity_seconds: values.offline_validity_minutes * 60,
  offline_sale_per_transaction_cents: toCents(values.offline_sale_per_transaction),
  offline_sale_per_customer_cents: toCents(values.offline_sale_per_customer),
  offline_sale_per_till_cents: toCents(values.offline_sale_per_till),
  offline_return_per_transaction_cents: toCents(values.offline_return_per_transaction),
  offline_return_per_customer_cents: toCents(values.offline_return_per_customer),
  offline_return_per_till_cents: toCents(values.offline_return_per_till),
});
