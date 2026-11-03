import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import * as React from "react";
import { TextDecoder, TextEncoder } from "util";

globalThis.TextEncoder = TextEncoder as typeof globalThis.TextEncoder;
globalThis.TextDecoder = TextDecoder as typeof globalThis.TextDecoder;

const mockUpdate = jest.fn();
const mockPayoutInfo = jest.fn(() => ({ in_payout_run: false, payout_date: null }));

jest.mock("@/api", () => ({
  useGetCustomerQuery: () => ({
    data: {
      balance: 10,
      donation: 20,
      iban: "DE89370400440532013000",
      account_name: "Jane Doe",
      email: "jane@example.com",
      has_entered_info: true,
      payout: { amount: 7, donation: 3 },
    },
  }),
  usePayoutInfoQuery: () => ({ data: mockPayoutInfo() }),
  useUpdateCustomerInfoMutation: () => [mockUpdate],
}));
jest.mock("@/components", () => ({
  PageContainer: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));
jest.mock("@/hooks", () => ({ useCurrencyFormatter: () => (amount: number) => `EUR ${amount.toFixed(2)}` }));
jest.mock("@/hooks/usePublicConfig", () => ({
  usePublicConfig: () => ({ donation_enabled: false, allowed_country_codes: ["DE"], translation_texts: {} }),
}));
jest.mock("@stustapay/components", () => ({ Loading: () => <div>Loading</div> }));
jest.mock("@stustapay/form-components", () => ({
  FormTextField: ({ name, formik }: { name: string; formik: { values: Record<string, string> } }) => (
    <input name={name} value={formik.values[name]} readOnly />
  ),
  FormCurrencyInput: () => <div>Donation</div>,
}));
jest.mock("@stustapay/utils", () => ({
  toFormikValidationSchema: (schema: { parseAsync: (values: unknown) => Promise<void> }) => ({
    validate: (values: unknown) => schema.parseAsync(values),
  }),
}));
jest.mock("@stustapay/modal-provider", () => ({ useOpenModal: () => jest.fn() }));
jest.mock("react-i18next", () => ({
  Trans: ({ children }: { children: React.ReactNode }) => <span>{children}</span>,
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: "en-US" } }),
}));
jest.mock("react-toastify", () => ({ toast: { success: jest.fn(), error: jest.fn() } }));

const { MemoryRouter } = require("react-router-dom");
const { PayoutInfo } = require("./PayoutInfo");

beforeEach(() => {
  mockPayoutInfo.mockReturnValue({ in_payout_run: false, payout_date: null });
});

test("ignores a saved donation when donations are disabled", async () => {
  mockUpdate.mockReturnValue({ unwrap: () => Promise.resolve() });
  render(
    <MemoryRouter>
      <PayoutInfo />
    </MemoryRouter>
  );

  expect(screen.getByText("EUR 10.00")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "payout.submitPayoutDataEdit" }));

  await waitFor(() =>
    expect(mockUpdate).toHaveBeenCalledWith({ customerBank: expect.objectContaining({ donation: 0 }) })
  );
});

test("shows the scheduled payout amount when donations are disabled", () => {
  mockPayoutInfo.mockReturnValue({ in_payout_run: true, payout_date: null });
  render(
    <MemoryRouter>
      <PayoutInfo />
    </MemoryRouter>
  );

  expect(screen.getByText("EUR 7.00")).toBeTruthy();
});
