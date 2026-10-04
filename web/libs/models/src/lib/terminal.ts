import { z } from "zod";

export const NewTerminalSchema = z.object({
  login_mode: z.enum(["personal", "device"]).optional().default("device"),
  device_role_id: z.number().int().optional().nullable(),
  device_cash_register_id: z.number().int().optional().nullable(),
  name: z.string(),
  description: z.string().optional().nullable(),
  mode: z.enum(["till", "entry", "exit"]).default("till"),
  entry_area_id: z.number().int().optional().nullable(),
  self_service: z.boolean().default(false),
  app_display_mode: z.enum(["day", "night"]).optional().nullable(),
});

export type NewTerminal = z.infer<typeof NewTerminalSchema>;

export const UpdateTerminalSchema = NewTerminalSchema.merge(
  z.object({ id: z.number(), login_mode: z.enum(["personal", "device"]).optional() })
);

export type UpdateTerminal = z.infer<typeof UpdateTerminalSchema>;
