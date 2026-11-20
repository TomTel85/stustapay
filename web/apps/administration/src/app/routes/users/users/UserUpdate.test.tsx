import * as React from "react";
import { fireEvent, render, screen } from "@testing-library/react";

const mockUseGetUserQuery = jest.fn();
const mockUseCurrentNode = jest.fn();
const mockUseParams = jest.fn();

jest.mock("@/api", () => ({
  useGetUserQuery: (...args: unknown[]) => mockUseGetUserQuery(...args),
  useUpdateUserMutation: () => [jest.fn()],
}));
jest.mock("@/components", () => ({
  EditLayout: ({ initialValues }: { initialValues: { login: string } }) => {
    const [login, setLogin] = require("react").useState(initialValues.login);
    return <input aria-label="login" value={login} onChange={(event) => setLogin(event.target.value)} />;
  },
}));
jest.mock("@/hooks", () => ({ useCurrentNode: () => mockUseCurrentNode() }));
jest.mock("@/app/layout", () => ({ withPrivilegeGuard: (_privilege: unknown, component: unknown) => component }));
jest.mock("@/app/routes", () => ({ UserRoutes: { detail: () => "/user" } }));
jest.mock("@stustapay/components", () => ({ Loading: () => <div>loading</div> }));
jest.mock("@stustapay/models", () => ({ UserSchema: {} }));
jest.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
jest.mock("react-router-dom", () => ({ useParams: () => mockUseParams() }));
jest.mock("./UserUpdateForm", () => ({ UserUpdateForm: () => null }));

const { UserUpdate } = require("./UserUpdate");

describe("UserUpdate", () => {
  beforeEach(() => {
    mockUseCurrentNode.mockReturnValue({ currentNode: { id: 5 } });
    mockUseParams.mockReturnValue({ userId: "12" });
    mockUseGetUserQuery.mockReturnValue({ currentData: { id: 12, node_id: 5, login: "original" } });
  });

  test("keeps a draft after a failed refetch and resets it for another context", () => {
    const { rerender } = render(<UserUpdate />);
    fireEvent.change(screen.getByLabelText("login"), { target: { value: "draft" } });

    mockUseGetUserQuery.mockReturnValue({ currentData: { id: 12, node_id: 5, login: "original" }, error: {} });
    rerender(<UserUpdate />);
    expect((screen.getByLabelText("login") as HTMLInputElement).value).toBe("draft");
    expect(screen.getByRole("alert").textContent).toBe("common.refreshError");

    mockUseCurrentNode.mockReturnValue({ currentNode: { id: 6 } });
    mockUseGetUserQuery.mockReturnValue({ currentData: { id: 12, node_id: 6, login: "other" } });
    rerender(<UserUpdate />);
    expect((screen.getByLabelText("login") as HTMLInputElement).value).toBe("other");
  });

  test("shows the initial loading error without a form", () => {
    mockUseGetUserQuery.mockReturnValue({ error: {} });
    render(<UserUpdate />);
    expect(screen.getByRole("alert").textContent).toBe("common.loadingError");
    expect(screen.queryByLabelText("login")).toBeNull();
  });
});
