import * as React from "react";
import { render, screen } from "@testing-library/react";
import { TextDecoder, TextEncoder } from "util";

(globalThis as typeof globalThis & { TextEncoder: typeof TextEncoder; TextDecoder: typeof TextDecoder }).TextEncoder =
  TextEncoder;
(globalThis as typeof globalThis & { TextEncoder: typeof TextEncoder; TextDecoder: typeof TextDecoder }).TextDecoder =
  TextDecoder;

const mockUseGetUserQuery = jest.fn();
const mockUseCurrentUserHasPrivilege = jest.fn();
const mockUseUserRoleAssignments = jest.fn();

jest.mock("../roleAssignments", () => ({
  ...jest.requireActual("../roleAssignments"),
  useUserRoleAssignments: () => mockUseUserRoleAssignments(),
}));

jest.mock("@/api", () => ({
  useGetUserQuery: (...args: unknown[]) => mockUseGetUserQuery(...args),
  useDeleteUserMutation: () => [jest.fn()],
}));

jest.mock("@/components", () => ({
  DetailLayout: ({ children }: { children: React.ReactNode; actions?: readonly unknown[] }) => <div>{children}</div>,
  DetailView: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DetailField: ({ label, value }: { label: string; value?: React.ReactNode }) => (
    <div>
      <span>{label}</span>
      <span>{value}</span>
    </div>
  ),
}));

jest.mock("@/hooks", () => ({
  useCurrentNode: () => ({ currentNode: { id: 5, name: "Bar" } }),
  useCurrentUserHasPrivilege: (...args: unknown[]) => mockUseCurrentUserHasPrivilege(...args),
}));

jest.mock("@/store", () => ({
  selectAuthToken: jest.fn(),
  useAppSelector: () => "test-token",
}));

jest.mock("@stustapay/modal-provider", () => ({
  useOpenModal: () => jest.fn(),
}));

jest.mock("@stustapay/components", () => ({
  Loading: () => <div>loading</div>,
}));

jest.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

jest.mock("react-router-dom", () => {
  const actual = jest.requireActual("react-router-dom") as typeof import("react-router-dom");
  return {
    ...actual,
    useNavigate: () => jest.fn(),
    useParams: () => ({ userId: "12" }),
  };
});

const { MemoryRouter } = require("react-router-dom");
const { UserDetail } = require("./UserDetail");

describe("UserDetail role assignment link", () => {
  beforeEach(() => {
    mockUseGetUserQuery.mockReset();
    mockUseGetUserQuery.mockReturnValue({
      currentData: {
        id: 12,
        node_id: 1,
        login: "parent-user",
        display_name: "Parent User",
        description: "",
        email: null,
        user_tag_id: null,
      },
      error: undefined,
    });
    mockUseCurrentUserHasPrivilege.mockReset();
    mockUseUserRoleAssignments.mockReturnValue({
      byUser: new Map([[12, [{ roleId: 7, roleName: "Kassierer", nodeId: 5, nodeName: "Bar", inherited: false }]]]),
      isLoading: false,
    });
  });

  test("links to assignment at the current node for a parent-created user", () => {
    mockUseCurrentUserHasPrivilege.mockReturnValue(true);

    render(
      <MemoryRouter>
        <UserDetail />
      </MemoryRouter>
    );

    expect(screen.getByRole("link", { name: "userToRole.assignAtNode" }).getAttribute("href")).toBe(
      "/node/5/user-to-roles/12/edit"
    );
    expect(screen.getByText("Kassierer")).toBeTruthy();
  });

  test("hides the assignment link without user management privilege", () => {
    mockUseCurrentUserHasPrivilege.mockReturnValue(false);

    render(
      <MemoryRouter>
        <UserDetail />
      </MemoryRouter>
    );

    expect(screen.queryByRole("link", { name: "userToRole.assignAtNode" })).toBeNull();
  });

  test("does not present failed role loading as an empty assignment", () => {
    mockUseUserRoleAssignments.mockReturnValue({ byUser: new Map(), error: { status: 500 } });
    render(
      <MemoryRouter>
        <UserDetail />
      </MemoryRouter>
    );
    expect(screen.getByText("common.loadingError")).toBeTruthy();
    expect(screen.queryByText("userToRole.noRoles")).toBeNull();
  });
});
