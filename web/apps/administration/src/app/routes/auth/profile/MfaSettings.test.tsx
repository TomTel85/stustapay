import * as React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MfaSettings } from "./MfaSettings";

const mockUpdate = jest.fn();
const mockRefetch = jest.fn();
let mockEnabled = false;
jest.mock("@/api", () => ({
  useGetMfaStatusQuery: () => ({ data: { enabled: mockEnabled, recovery_codes_remaining: 10 }, refetch: mockRefetch }),
  useUpdateMfaMutation: () => [mockUpdate, { isLoading: false, reset: jest.fn() }],
}));
jest.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
jest.mock("react-qr-code", () => ({ __esModule: true, default: () => <div>QR code</div> }));

beforeEach(() => {
  mockUpdate.mockReset();
  mockRefetch.mockReset();
  mockEnabled = false;
});

test("enrolls with a verified code and shows recovery codes only until acknowledged", async () => {
  mockUpdate
    .mockReturnValueOnce({
      unwrap: () => Promise.resolve({ success: true, secret: "TESTKEY", provisioning_uri: "otpauth://totp/test" }),
    })
    .mockReturnValueOnce({ unwrap: () => Promise.resolve({ success: true, recovery_codes: ["RECOVERY-1"] }) });
  render(<MfaSettings />);
  expect(screen.queryByLabelText(/auth.mfa.password/)).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "auth.mfa.setup" }));
  await screen.findByText("QR code");
  expect(mockUpdate).toHaveBeenNthCalledWith(1, { mfaUpdate: { action: "setup", password: "", code: "" } });
  expect(screen.queryByLabelText(/auth.mfa.password/)).toBeNull();
  expect((screen.getByLabelText("auth.mfa.secret") as HTMLInputElement).value).toBe("TESTKEY");
  fireEvent.change(screen.getByLabelText(/auth.mfa.code/), { target: { value: "123456" } });
  fireEvent.click(screen.getByRole("button", { name: "auth.mfa.confirm" }));
  await screen.findByRole("dialog");
  expect(mockUpdate).toHaveBeenCalledTimes(1);
  fireEvent.change(screen.getByLabelText(/auth.mfa.password/), { target: { value: "test-password" } });
  fireEvent.click(screen.getByRole("button", { name: "confirm", exact: true }));
  await screen.findByText("RECOVERY-1");
  await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  expect(mockUpdate).toHaveBeenLastCalledWith({
    mfaUpdate: { action: "enable", password: "test-password", code: "123456" },
  });
  expect(screen.queryByText("QR code")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "auth.mfa.savedRecovery" }));
  expect(screen.queryByText("RECOVERY-1")).toBeNull();
  await waitFor(() => expect(screen.queryByLabelText(/auth.mfa.password/)).toBeNull());
});

test("shows server verification failures without hiding the setup", async () => {
  mockUpdate.mockReturnValue({ unwrap: () => Promise.resolve({ success: false, error: "rate_limited" }) });
  render(<MfaSettings />);
  fireEvent.click(screen.getByRole("button", { name: "auth.mfa.setup" }));
  await screen.findByRole("alert");
  expect(screen.getByText("auth.mfa.errors.rate_limited")).toBeTruthy();
});

test.each([
  ["auth.mfa.disable", "disable"],
  ["auth.mfa.regenerate", "regenerate"],
])("confirms %s with a password dialog before changing MFA", async (button, action) => {
  mockEnabled = true;
  mockUpdate.mockReturnValue({ unwrap: () => Promise.resolve({ success: true }) });
  render(<MfaSettings />);
  expect(screen.queryByLabelText(/auth.mfa.password/)).toBeNull();
  fireEvent.change(screen.getByLabelText(/auth.mfa.code/), { target: { value: "RECOVERY-1" } });
  fireEvent.click(screen.getByRole("button", { name: button }));
  await screen.findByRole("dialog");
  expect(mockUpdate).not.toHaveBeenCalled();
  fireEvent.change(screen.getByLabelText(/auth.mfa.password/), { target: { value: "test-password" } });
  fireEvent.click(screen.getByRole("button", { name: "confirm", exact: true }));
  await waitFor(() =>
    expect(mockUpdate).toHaveBeenCalledWith({
      mfaUpdate: { action, password: "test-password", code: "RECOVERY-1" },
    })
  );
  await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
});

test("cancelling confirmation makes no change and clears the password before reopening", async () => {
  mockEnabled = true;
  render(<MfaSettings />);
  fireEvent.change(screen.getByLabelText(/auth.mfa.code/), { target: { value: "123456" } });
  fireEvent.click(screen.getByRole("button", { name: "auth.mfa.regenerate" }));
  fireEvent.change(await screen.findByLabelText(/auth.mfa.password/), { target: { value: "do-not-keep" } });
  fireEvent.click(screen.getByRole("button", { name: "cancel", exact: true }));
  await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  expect(mockUpdate).not.toHaveBeenCalled();
  expect((screen.getByLabelText(/auth.mfa.code/) as HTMLInputElement).value).toBe("123456");
  fireEvent.click(screen.getByRole("button", { name: "auth.mfa.regenerate" }));
  expect(((await screen.findByLabelText(/auth.mfa.password/)) as HTMLInputElement).value).toBe("");
});

test("keeps confirmation open on a wrong password and allows retry", async () => {
  mockEnabled = true;
  mockUpdate
    .mockReturnValueOnce({ unwrap: () => Promise.resolve({ success: false, error: "invalid_credentials" }) })
    .mockReturnValueOnce({ unwrap: () => Promise.resolve({ success: true }) });
  render(<MfaSettings />);
  fireEvent.change(screen.getByLabelText(/auth.mfa.code/), { target: { value: "123456" } });
  fireEvent.click(screen.getByRole("button", { name: "auth.mfa.disable" }));
  fireEvent.change(await screen.findByLabelText(/auth.mfa.password/), { target: { value: "wrong" } });
  fireEvent.click(screen.getByRole("button", { name: "confirm", exact: true }));
  await screen.findByText("auth.mfa.errors.invalid_credentials");
  expect(screen.getByRole("dialog")).toBeTruthy();
  expect((screen.getByLabelText(/auth.mfa.password/) as HTMLInputElement).value).toBe("");
  fireEvent.change(screen.getByLabelText(/auth.mfa.password/), { target: { value: "correct" } });
  fireEvent.click(screen.getByRole("button", { name: "confirm", exact: true }));
  await waitFor(() =>
    expect(mockUpdate).toHaveBeenLastCalledWith({
      mfaUpdate: { action: "disable", password: "correct", code: "123456" },
    })
  );
});
