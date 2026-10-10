import { EventSumUpSettingsSchema } from "./sumupEnvironment";

describe("EventSumUpSettingsSchema", () => {
  const baseSettings = {
    sumup_topup_enabled: true,
    group_topup_enabled: false,
    sumup_payment_enabled: true,
  };

  it.each(["live", "sandbox"] as const)("accepts the %s environment", (sumup_environment) => {
    expect(EventSumUpSettingsSchema.parse({ ...baseSettings, sumup_environment }).sumup_environment).toBe(
      sumup_environment,
    );
  });

  it("requires an explicit environment", () => {
    expect(EventSumUpSettingsSchema.safeParse(baseSettings).success).toBe(false);
  });
});
