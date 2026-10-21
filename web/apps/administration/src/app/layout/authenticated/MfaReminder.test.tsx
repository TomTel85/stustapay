import { render, screen } from "@testing-library/react";
import { TextDecoder, TextEncoder } from "util";

Object.assign(globalThis, { TextDecoder, TextEncoder });

const mockMfaStatus = jest.fn();
jest.mock("@/api", () => ({ useGetMfaStatusQuery: () => mockMfaStatus() }));
jest.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));

const { MemoryRouter } = require("react-router-dom");
const { MfaReminder } = require("./MfaReminder");

const renderReminder = () =>
  render(
    <MemoryRouter>
      <MfaReminder />
    </MemoryRouter>
  );

beforeEach(() => mockMfaStatus.mockReset());

test("reminds unenrolled users and links directly to their profile", () => {
  mockMfaStatus.mockReturnValue({ data: { enabled: false, recovery_codes_remaining: 0 } });
  renderReminder();
  expect(screen.getByRole("alert").textContent).toContain("auth.mfa.reminderText");
  expect(screen.getByRole("link", { name: "auth.mfa.setup" }).getAttribute("href")).toBe("/profile");
});

test("removes the reminder as soon as the account has MFA enabled", () => {
  mockMfaStatus.mockReturnValue({ data: { enabled: false } });
  const view = renderReminder();
  expect(screen.getByRole("alert")).toBeTruthy();
  mockMfaStatus.mockReturnValue({ data: { enabled: true } });
  view.rerender(
    <MemoryRouter>
      <MfaReminder />
    </MemoryRouter>
  );
  expect(screen.queryByRole("alert")).toBeNull();
});

test.each([
  { data: undefined, isLoading: true },
  { data: undefined, error: { status: 503 } },
  { data: { enabled: false }, error: { status: 503 } },
])("does not show an enrollment claim while status is unavailable: %j", (result) => {
  mockMfaStatus.mockReturnValue(result);
  renderReminder();
  expect(screen.queryByRole("alert")).toBeNull();
});
