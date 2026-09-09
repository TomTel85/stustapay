import { TextDecoder, TextEncoder } from "util";
import iban from "iban";
import { DEFAULT_PAYOUT_COUNTRY_CODES, PayoutSettingsSchema } from "./TabPayout.schema";

declare global {
  // eslint-disable-next-line no-var
  var TextEncoder: typeof globalThis.TextEncoder;
  // eslint-disable-next-line no-var
  var TextDecoder: typeof globalThis.TextDecoder;
}

globalThis.TextEncoder = TextEncoder as typeof globalThis.TextEncoder;
globalThis.TextDecoder = TextDecoder as typeof globalThis.TextDecoder;

describe("PayoutSettingsSchema", () => {
  test("defaults to all EU payout countries", () => {
    const settings = PayoutSettingsSchema.parse({
      translation_texts: {},
      payout_email_enabled: false,
      payout_reminder_enabled: false,
      payout_reminder_weekday: 0,
      payout_reminder_time: "09:00",
      payout_reminder_user_ids: [],
      sepa_enabled: false,
      sepa_sender_name: "",
      sepa_sender_iban: undefined,
      sepa_description: "",
      payout_done_subject: undefined,
      payout_done_message: undefined,
      payout_registered_subject: undefined,
      payout_registered_message: undefined,
      payout_sender: undefined,
    });

    expect(settings.sepa_allowed_country_codes).toEqual(DEFAULT_PAYOUT_COUNTRY_CODES);
    expect(DEFAULT_PAYOUT_COUNTRY_CODES).toHaveLength(27);
    expect(DEFAULT_PAYOUT_COUNTRY_CODES.every((countryCode) => countryCode in iban.countries)).toBe(true);
    expect(DEFAULT_PAYOUT_COUNTRY_CODES).not.toContain("CH");
    expect(DEFAULT_PAYOUT_COUNTRY_CODES).not.toContain("GB");
  });

  test("accepts optional payout disabled notices via translation_texts", () => {
    expect(
      PayoutSettingsSchema.parse({
        translation_texts: {
          "de-DE": { payout_disabled_notice: "Nur nach dem Event" },
          "en-US": { payout_disabled_notice: "Only after the event" },
        },
        payout_email_enabled: false,
        payout_reminder_enabled: false,
        payout_reminder_weekday: 0,
        payout_reminder_time: "09:00",
        payout_reminder_user_ids: [],
        sepa_enabled: false,
        sepa_sender_name: "",
        sepa_sender_iban: undefined,
        sepa_description: "",
        sepa_allowed_country_codes: [],
        payout_done_subject: undefined,
        payout_done_message: undefined,
        payout_registered_subject: undefined,
        payout_registered_message: undefined,
        payout_sender: undefined,
      })
    ).toMatchObject({
      translation_texts: {
        "de-DE": { payout_disabled_notice: "Nur nach dem Event" },
        "en-US": { payout_disabled_notice: "Only after the event" },
      },
    });
  });

  test("allows empty translation_texts so the portal can fall back to built-in copy", () => {
    expect(
      PayoutSettingsSchema.parse({
        translation_texts: {},
        payout_email_enabled: false,
        payout_reminder_enabled: false,
        payout_reminder_weekday: 0,
        payout_reminder_time: "09:00",
        payout_reminder_user_ids: [],
        sepa_enabled: false,
        sepa_sender_name: "",
        sepa_sender_iban: undefined,
        sepa_description: "",
        sepa_allowed_country_codes: [],
        payout_done_subject: undefined,
        payout_done_message: undefined,
        payout_registered_subject: undefined,
        payout_registered_message: undefined,
        payout_sender: undefined,
      })
    ).toMatchObject({
      translation_texts: {},
    });
  });
});
