import { RestrictedEventSettings } from "@/api";
import { OfflineFormSchema, offlineSettingDefaults, toOfflineApiSettings, toOfflineFormValues } from "./offlineSettings";

describe("offline event settings mapping", () => {
  test("uses safe defaults and converts API cents to editable euro amounts", () => {
    const values = toOfflineFormValues({} as RestrictedEventSettings);

    expect(values.offline_enabled).toBe(false);
    expect(values.offline_validity_minutes).toBe(120);
    expect(values.offline_sale_per_transaction).toBe(20);
    expect(values.offline_sale_per_customer).toBe(30);
    expect(values.offline_sale_per_till).toBe(500);
    expect(values.offline_return_per_transaction).toBe(20);
    expect(values.offline_return_per_customer).toBe(30);
    expect(values.offline_return_per_till).toBe(500);
    expect(offlineSettingDefaults.offline_enabled).toBe(false);
  });

  test("round trips configured limits as integer cents and seconds", () => {
    const values = OfflineFormSchema.parse({
      ...toOfflineFormValues({} as RestrictedEventSettings),
      offline_enabled: true,
      offline_validity_minutes: 90,
      offline_sale_per_transaction: 12.35,
      offline_return_per_till: 0,
    });

    expect(toOfflineApiSettings(values)).toMatchObject({
      offline_enabled: true,
      offline_validity_seconds: 5400,
      offline_sale_per_transaction_cents: 1235,
      offline_return_per_till_cents: 0,
    });
  });

  test("rejects validity outside one day and currency with more than two decimals", () => {
    const values = toOfflineFormValues({} as RestrictedEventSettings);

    expect(() => OfflineFormSchema.parse({ ...values, offline_validity_minutes: 1441 })).toThrow();
    expect(() => OfflineFormSchema.parse({ ...values, offline_sale_per_transaction: 2.345 })).toThrow();
  });
});
