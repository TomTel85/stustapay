import * as React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { TextDecoder, TextEncoder } from "util";

(globalThis as typeof globalThis & { TextEncoder: typeof TextEncoder; TextDecoder: typeof TextDecoder }).TextEncoder =
  TextEncoder;
(globalThis as typeof globalThis & { TextEncoder: typeof TextEncoder; TextDecoder: typeof TextDecoder }).TextDecoder =
  TextDecoder;

const mockUseAppSelector = jest.fn();
const mockLogin = jest.fn();
const mockNavigate = jest.fn();

jest.mock("@/api", () => ({
  useLoginMutation: () => [mockLogin],
}));

jest.mock("@/store", () => ({
  selectIsAuthenticated: "selectIsAuthenticated",
  useAppSelector: (...args: unknown[]) => mockUseAppSelector(...args),
}));

jest.mock("@stustapay/form-components", () => ({
  FormTextField: ({
    name,
    label,
    formik,
    type,
  }: {
    name: string;
    label: string;
    formik: { values: Record<string, string>; handleChange: (event: React.ChangeEvent<HTMLInputElement>) => void };
    type?: string;
  }) => <input aria-label={label} name={name} type={type} value={formik.values[name]} onChange={formik.handleChange} />,
}));

jest.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, options?: { username?: string }) =>
      key === "auth.invitationLoginHint" ? `invitation-hint:${options?.username}` : key,
  }),
}));

jest.mock("react-router-dom", () => {
  const actual = jest.requireActual("react-router-dom");
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

jest.mock("react-toastify", () => ({
  toast: {
    error: jest.fn(),
  },
}));

const { MemoryRouter } = require("react-router-dom");
const { Login } = require("./Login");

describe("Login", () => {
  beforeEach(() => {
    mockUseAppSelector.mockReset();
    mockLogin.mockReset();
    mockNavigate.mockReset();
    mockUseAppSelector.mockReturnValue(false);
  });

  test("prefills the username and shows a first-login hint after invitation acceptance", () => {
    render(
      <MemoryRouter initialEntries={["/login?username=crew-user&invitationAccepted=1"]}>
        <Login />
      </MemoryRouter>
    );

    expect((screen.getByLabelText("auth.username") as HTMLInputElement).value).toBe("crew-user");
    expect(screen.getByText("invitation-hint:crew-user")).toBeTruthy();
  });

  test("keeps the normal login form when opened directly", () => {
    render(
      <MemoryRouter initialEntries={["/login"]}>
        <Login />
      </MemoryRouter>
    );

    expect((screen.getByLabelText("auth.username") as HTMLInputElement).value).toBe("");
    expect(screen.queryByText(/invitation-hint:/)).toBeNull();
  });
  test("requests a second factor without dropping the password and submits the code", async () => {
    mockLogin.mockReturnValue({
      unwrap: () => Promise.resolve({ success: null, available_nodes: null, mfa_required: true }),
    });
    render(
      <MemoryRouter initialEntries={["/login"]}>
        <Login />
      </MemoryRouter>
    );
    fireEvent.change(screen.getByLabelText("auth.username"), { target: { value: "admin" } });
    fireEvent.change(screen.getByLabelText("auth.password"), { target: { value: "test-password" } });
    fireEvent.click(screen.getByRole("button", { name: "auth.login" }));
    await screen.findByLabelText("auth.mfa.code");
    expect((screen.getByLabelText("auth.password") as HTMLInputElement).value).toBe("test-password");
    fireEvent.change(screen.getByLabelText("auth.mfa.code"), { target: { value: "123456" } });
    fireEvent.click(screen.getByRole("button", { name: "auth.login" }));
    await waitFor(() =>
      expect(mockLogin).toHaveBeenLastCalledWith({
        loginPayload: { username: "admin", password: "test-password", node_id: null, mfa_code: "123456" },
      })
    );
  });

  test("keeps the selected node when it requires MFA", async () => {
    mockLogin
      .mockReturnValueOnce({
        unwrap: () =>
          Promise.resolve({
            success: null,
            available_nodes: [
              { node_id: 11, name: "Festival A", description: "A" },
              { node_id: 12, name: "Festival B", description: "B" },
            ],
          }),
      })
      .mockReturnValue({ unwrap: () => Promise.resolve({ success: null, available_nodes: null, mfa_required: true }) });
    render(
      <MemoryRouter initialEntries={["/login"]}>
        <Login />
      </MemoryRouter>
    );
    fireEvent.change(screen.getByLabelText("auth.username"), { target: { value: "admin" } });
    fireEvent.change(screen.getByLabelText("auth.password"), { target: { value: "test-password" } });
    fireEvent.click(screen.getByRole("button", { name: "auth.login" }));
    fireEvent.click(await screen.findByText("Festival B"));
    await screen.findByLabelText("auth.mfa.code");
    fireEvent.change(screen.getByLabelText("auth.mfa.code"), { target: { value: "123456" } });
    fireEvent.click(screen.getByRole("button", { name: "auth.login" }));
    await waitFor(() =>
      expect(mockLogin).toHaveBeenLastCalledWith({
        loginPayload: { username: "admin", password: "test-password", node_id: 12, mfa_code: "123456" },
      })
    );
  });
});
