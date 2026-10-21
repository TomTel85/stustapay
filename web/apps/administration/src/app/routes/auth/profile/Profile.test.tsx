import { fireEvent, render, screen } from "@testing-library/react";
import { TextDecoder, TextEncoder } from "util";

Object.assign(globalThis, { TextDecoder, TextEncoder });

const { Profile } = require("./Profile");

jest.mock("@stustapay/form-components", () => ({ FormTextField: () => <input aria-label="email" /> }));

jest.mock("@/api", () => ({ useUpdateProfileMutation: () => [jest.fn()] }));
jest.mock("@/components/features", () => ({ ThemeSelect: () => null }));
jest.mock("@/hooks", () => ({ useCurrentUser: () => ({ login: "admin", display_name: "Admin", email: "" }) }));
jest.mock("@/store", () => ({ useAppDispatch: () => jest.fn() }));
jest.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
jest.mock("../../../../i18n", () => ({ __esModule: true, default: { t: (key: string) => key } }));
jest.mock("./MfaSettings", () => ({ MfaSettings: () => <div>MFA settings</div> }));
jest.mock("./PasswordChange", () => ({
  PasswordChange: () => <input aria-label="current password" type="password" />,
}));

test("keeps password inputs hidden until requested and clears them when cancelled", () => {
  render(<Profile />);
  expect(screen.queryByLabelText("current password")).toBeNull();
  const toggle = screen.getByRole("button", { name: "auth.changePassword" });
  expect(toggle.getAttribute("aria-expanded")).toBe("false");
  fireEvent.click(toggle);
  expect(toggle.getAttribute("aria-expanded")).toBe("true");
  fireEvent.change(screen.getByLabelText("current password"), { target: { value: "temporary entry" } });
  fireEvent.click(screen.getByRole("button", { name: "cancel" }));
  expect(screen.queryByLabelText("current password")).toBeNull();
  fireEvent.click(toggle);
  expect((screen.getByLabelText("current password") as HTMLInputElement).value).toBe("");
  expect(screen.getByText("MFA settings")).toBeTruthy();
});
