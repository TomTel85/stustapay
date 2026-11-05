import * as React from "react";
import { render, renderHook, screen } from "@testing-library/react";

const mockUseListUserToRoleQuery = jest.fn();
const mockUseListUserRolesQuery = jest.fn();
const root = {
  id: 0,
  name: "Root",
  children: [{ id: 5, name: "Current", children: [] }],
};

jest.mock("@/api", () => ({
  findNode: (nodeId: number, node: typeof root): typeof root | undefined => {
    if (node.id === nodeId) return node;
    for (const child of node.children) {
      const found = (
        jest.requireMock("@/api") as { findNode: (id: number, node: typeof root) => typeof root | undefined }
      ).findNode(nodeId, child);
      if (found) return found;
    }
    return undefined;
  },
  useListUserRolesQuery: (...args: unknown[]) => mockUseListUserRolesQuery(...args),
  useListUserToRoleQuery: (...args: unknown[]) => mockUseListUserToRoleQuery(...args),
  useNodeTree: () => ({ root }),
}));

jest.mock("@/hooks", () => ({ useCurrentNode: () => ({ currentNode: { id: 5, name: "Current" } }) }));
jest.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, values?: { role: string; node: string }) =>
      key === "userToRole.inheritedFrom" ? `${values?.role} (from ${values?.node})` : key,
  }),
}));

const { RoleAssignmentSummary, useUserRoleAssignments } =
  require("./roleAssignments") as typeof import("./roleAssignments");

describe("user role assignments", () => {
  beforeEach(() => {
    mockUseListUserToRoleQuery.mockReset().mockReturnValue({
      currentData: [
        { user_id: 10, node_id: 0, role_ids: [2] },
        { user_id: 10, node_id: 5, role_ids: [2] },
        { user_id: 11, node_id: 5, role_ids: [] },
      ],
      isLoading: false,
      error: undefined,
    });
    mockUseListUserRolesQuery.mockReset().mockReturnValue({
      currentData: { ids: [2], entities: { 2: { id: 2, node_id: 0, name: "Manager", privileges: [] } } },
      isLoading: false,
      error: undefined,
    });
  });

  test("keeps inherited and local copies of a role with their assignment origins", () => {
    const { result } = renderHook(() => useUserRoleAssignments());
    expect(result.current.byUser.get(10)).toEqual([
      { roleId: 2, roleName: "Manager", nodeId: 0, nodeName: "Root", inherited: true },
      { roleId: 2, roleName: "Manager", nodeId: 5, nodeName: "Current", inherited: false },
    ]);
    expect(result.current.byUser.get(11)).toEqual([]);
  });

  test("renders inherited origin, local role, and empty state as inline text", () => {
    const { result } = renderHook(() => useUserRoleAssignments());
    const assignments = (result.current.byUser.get(10) ?? []);
    const { rerender } = render(
      <p>
        <RoleAssignmentSummary assignments={assignments} />
      </p>
    );
    expect(screen.getByText("Manager (from Root); Manager")).toBeTruthy();
    rerender(
      <p>
        <RoleAssignmentSummary assignments={[]} />
      </p>
    );
    expect(screen.getByText("userToRole.noRoles")).toBeTruthy();
  });

  test("keeps assignments with missing role or node metadata visible", () => {
    mockUseListUserToRoleQuery.mockReturnValue({
      currentData: [{ user_id: 12, node_id: 123, role_ids: [999] }],
      isLoading: false,
      error: undefined,
    });
    mockUseListUserRolesQuery.mockReturnValue({
      currentData: { ids: [], entities: {} },
      isLoading: false,
      error: undefined,
    });

    const { result } = renderHook(() => useUserRoleAssignments());
    expect(result.current.byUser.get(12)).toEqual([
      { roleId: 999, roleName: "#999", nodeId: 123, nodeName: "#123", inherited: true },
    ]);
    const { rerender } = render(<RoleAssignmentSummary assignments={(result.current.byUser.get(12) ?? [])} />);
    expect(screen.getByText("#999 (from #123)")).toBeTruthy();
    rerender(<RoleAssignmentSummary assignments={[]} />);
    expect(screen.getByText("userToRole.noRoles")).toBeTruthy();
  });

  test("reports combined loading and query errors", () => {
    mockUseListUserToRoleQuery.mockReturnValue({ currentData: undefined, isLoading: true, error: undefined });
    mockUseListUserRolesQuery.mockReturnValue({ currentData: undefined, isLoading: false, error: { status: 500 } });

    const { result } = renderHook(() => useUserRoleAssignments());
    expect(result.current.isLoading).toBe(true);
    expect(result.current.error).toEqual({ status: 500 });
  });

  test("does not use the previous node's assignments while the current node is loading", () => {
    mockUseListUserToRoleQuery.mockReturnValue({
      data: [{ user_id: 10, node_id: 0, role_ids: [2] }],
      currentData: undefined,
      isLoading: false,
    });
    const { result } = renderHook(() => useUserRoleAssignments());
    expect(result.current.isLoading).toBe(true);
    expect(result.current.byUser.size).toBe(0);
  });
});
