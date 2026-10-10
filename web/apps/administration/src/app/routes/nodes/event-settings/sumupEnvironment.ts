import { z } from "zod";

export const EventSumUpSettingsSchema = z.object({
  sumup_topup_enabled: z.boolean(),
  group_topup_enabled: z.boolean(),
  sumup_payment_enabled: z.boolean(),
  sumup_environment: z.enum(["live", "sandbox"]),
});

export type EventSumUpSettings = z.infer<typeof EventSumUpSettingsSchema>;
