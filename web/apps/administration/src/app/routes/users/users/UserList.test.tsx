import * as React from "react";
import { render, screen } from "@testing-library/react";
import { TextDecoder, TextEncoder } from "util";

Object.assign(globalThis, { TextEncoder, TextDecoder });

const mockUsersQuery = jest.fn();
const mockUseUserRoleAssignments = jest.fn();
const mockRows = [
  { id: 10, login: "alex", display_name: "Alex", email: "alex@example.com", description: "", node_id: 5 },
  { id: 11, login: "child-user", display_name: "Child User", email: "", description: "", node_id: 6 },
  { id: 12, login: "parent-user", display_name: "Parent User", email: "", description: "", node_id: 1 },
];

jest.mock("@/api", () => ({
  selectUserAll: () => mockRows,
  useListUsersQuery: (...args: unknown[]) => mockUsersQuery(...args),
  useDeleteUserMutation: () => [jest.fn()],
}));
jest.mock("@/app/routes", () => ({
  UserRoutes: { privilege: "users", detail: (id: number, nodeId: number) => `/node/${nodeId}/users/${id}` },
  UserTagRoutes: { detail: (id: number) => `/tags/${id}` },
}));
jest.mock("@/components", () => ({
  ListLayout: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));
jest.mock("@/hooks", () => ({
  useCurrentNode: () => ({ currentNode: { id: 5, name: "Current", parent_ids: [1] } }),
  useCurrentUserHasPrivilege: () => false,
  useCurrentUserHasPrivilegeAtNode: () => () => false,
  useRenderNode: () => ({ dataGridNodeColumn: { field: "node_id", headerName: "node" } }),
}));
jest.mock("@stustapay/framework", () => ({
  DataGrid: ({
    rows: gridRows,
    columns,
  }: {
    rows: typeof mockRows;
    columns: Array<{
      field: string;
      headerName?: string;
      renderCell?: (params: { row: (typeof mockRows)[number] }) => React.ReactNode;
    }>;
  }) => (
    <div>
      {columns.map((column) => (
        <span key={column.field}>{column.headerName}</span>
      ))}
      {gridRows.flatMap((row) =>
        columns.map((column) => (
          <div key={`${row.id}-${column.field}`} data-testid={column.field}>
            {column.renderCell?.({ row })}
          </div>
        ))
      )}
    </div>
  ),
  GridActionsCellItem: () => null,
}));
jest.mock("@stustapay/components", () => ({ Loading: () => <div>loading</div> }));
jest.mock("@stustapay/modal-provider", () => ({ useOpenModal: () => jest.fn() }));
jest.mock("../roleAssignments", () => ({
  ...jest.requireActual("../roleAssignments"),
  useUserRoleAssignments: (...args: unknown[]) => mockUseUserRoleAssignments(...args),
}));
jest.mock("react-i18next", () => ({
  useTranslation: () => ({
    i18n: { resolvedLanguage: "en" },
    t: (key: string, values?: { role: string; node: string }) =>
      key === "userToRole.inheritedFrom" ? `${values?.role} (from ${values?.node})` : key,
  }),
}));
jest.mock("react-router-dom", () => ({
  Link: ({ children, to }: { children: React.ReactNode; to: string }) => <a href={to}>{children}</a>,
  useNavigate: () => jest.fn(),
}));

const { UserList } = require("./UserList") as typeof import("./UserList");

describe("UserList role summary", () => {
  beforeEach(() => {
    mockUsersQuery.mockImplementation((_: unknown, options: { selectFromResult: (value: unknown) => unknown }) =>
      options.selectFromResult({ currentData: { ids: [10], entities: { 10: mockRows[0] } }, isLoading: false })
    );
    mockUseUserRoleAssignments.mockReturnValue({
      byUser: new Map([
        [
          10,
          [
            { roleId: 2, roleName: "Local", nodeId: 5, nodeName: "Current", inherited: false },
            { roleId: 3, roleName: "Inherited", nodeId: 0, nodeName: "Root", inherited: true },
          ],
        ],
      ]),
      isLoading: false,
      error: undefined,
    });
  });

  test("shows local and inherited roles together for each user", () => {
    render(<UserList />);
    expect(screen.getByText("user.roles")).toBeTruthy();
    expect(screen.getByText("Local; Inherited (from Root)")).toBeTruthy();
  });

  test("opens child-owned users at their workspace and inherited users at the current workspace", () => {
    render(<UserList />);
    expect(screen.getByRole("link", { name: "alex" }).getAttribute("href")).toBe("/node/5/users/10");
    expect(screen.getByRole("link", { name: "child-user" }).getAttribute("href")).toBe("/node/6/users/11");
    expect(screen.getByRole("link", { name: "parent-user" }).getAttribute("href")).toBe("/node/5/users/12");
  });

  test("shows an error instead of silently treating failed role data as empty", () => {
    mockUseUserRoleAssignments.mockReturnValue({ byUser: new Map(), isLoading: true, error: new Error("failed") });
    render(<UserList />);
    expect(screen.getByRole("alert").textContent).toBe("userToRole.loadError");
    expect(screen.getByRole("link", { name: "alex" })).toBeTruthy();
  });

  test("keeps the user grid usable while role data loads", () => {
    mockUseUserRoleAssignments.mockReturnValue({ byUser: new Map(), isLoading: true, error: undefined });
    render(<UserList />);
    expect(screen.getByRole("link", { name: "alex" })).toBeTruthy();
    expect(screen.getAllByText("userToRole.loadingRoles")).toHaveLength(mockRows.length);
  });
});
