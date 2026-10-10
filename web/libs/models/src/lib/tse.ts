import { z } from "zod";

export const TseTypeSchema = z.enum(["diebold_nixdorf", "fiskaly"]);
export type TseType = z.infer<typeof TseTypeSchema>;

const TseConnectionFields = {
  name: z.string().min(1),
  ws_url: z.string().default(""),
  ws_timeout: z.number().default(5),
  password: z.string().default(""),
  fiskaly_profile: z.string().nullable().optional(),
};

export const UpdateTseSchema = z
  .object({
    ...TseConnectionFields,
    // The provider is included in the edit form only as a validation discriminator.
    // The administration API keeps it immutable and does not accept it in updates.
    type: TseTypeSchema.optional(),
  })
  .superRefine((tse, ctx) => {
    if (tse.type === "fiskaly") {
      if (!tse.fiskaly_profile?.trim()) {
        ctx.addIssue({ code: "custom", path: ["fiskaly_profile"], message: "Required" });
      }
    } else if (!tse.ws_url.trim()) {
      ctx.addIssue({ code: "custom", path: ["ws_url"], message: "Required" });
    }
  });
export type UpdateTse = z.infer<typeof UpdateTseSchema>;

export const NewTseSchema = z
  .object({
    ...TseConnectionFields,
    serial: z.string().nullable().default(null),
    type: TseTypeSchema,
  })
  .superRefine((tse, ctx) => {
    if (tse.type === "fiskaly") {
      if (!tse.fiskaly_profile?.trim()) {
        ctx.addIssue({ code: "custom", path: ["fiskaly_profile"], message: "Required" });
      }
    } else {
      if (!tse.serial?.trim()) {
        ctx.addIssue({ code: "custom", path: ["serial"], message: "Required" });
      }
      if (!tse.ws_url.trim()) {
        ctx.addIssue({ code: "custom", path: ["ws_url"], message: "Required" });
      }
    }
  });
export type NewTse = z.infer<typeof NewTseSchema>;
