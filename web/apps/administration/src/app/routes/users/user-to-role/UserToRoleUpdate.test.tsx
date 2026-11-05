import * as React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { UserToRoleUpdate } from "./UserToRoleUpdate";

const mockUpdate = jest.fn();
const mockAssignmentsQuery = jest.fn();
const mockUserQuery = jest.fn();
const mockCurrentNode = { id: 5, name: "Bar" };
jest.mock("../roleAssignments", () => ({
  ...jest.requireActual("../roleAssignments"),
  useUserRoleAssignments: () => ({
    byUser: new Map([[12, [{ roleId: 99, roleName: "Orga", nodeId: 1, nodeName: "Event", inherited: true }]]]),
    isLoading: false,
  }),
}));

jest.mock("@/api", () => ({
  useListUserToRoleQuery: (...args: unknown[]) => mockAssignmentsQuery(...args),
  useGetUserQuery: (...args: unknown[]) => mockUserQuery(...args),
  useUpdateUserToRolesMutation: () => [mockUpdate],
}));
jest.mock("@/hooks", () => ({ useCurrentNode: () => ({ currentNode: mockCurrentNode }) }));
jest.mock("@/app/layout", () => ({ withPrivilegeGuard: (_: unknown, component: unknown) => component }));
jest.mock("@/components/features", () => ({ RoleSelect: ({ label }: { label: string }) => <div>{label}</div> }));
jest.mock("@/components", () => {
  const { useState } = jest.requireActual("react") as typeof React;
  const Layout = ({
    title,
    submitLabel,
    initialValues,
    onSubmit,
    successRoute,
    form: ChildForm,
  }: {
    title: string;
    submitLabel: string;
    initialValues: { user_id: number; role_ids: number[] };
    onSubmit: (values: { user_id: number; role_ids: number[] }) => void;
    successRoute: string;
    form: React.ComponentType<Record<string, unknown>>;
  }) => {
    const [values] = useState(initialValues);
    return (
      <div>
        <h1>{title}</h1>
        <span>{successRoute}</span>
        <ChildForm values={values} errors={{}} touched={{}} setFieldValue={jest.fn()} />
        <button onClick={() => onSubmit(values)}>{submitLabel}</button>
      </div>
    );
  };
  return { CreateLayout: Layout, EditLayout: Layout };
});
jest.mock("@stustapay/components", () => ({ Loading: () => <div>loading</div> }));
jest.mock("react-router-dom", () => ({ useParams: () => ({ userId: "12" }) }));
jest.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, values?: Record<string, string>) => (values ? `${key}: ${Object.values(values).join(", ")}` : key),
  }),
}));

describe("UserToRoleUpdate", () => {
  beforeEach(() => {
    mockCurrentNode.id = 5;
    mockUpdate.mockReset();
    mockUserQuery.mockReturnValue({ currentData: { id: 12, node_id: 1, login: "alex", display_name: "Alex" } });
    mockAssignmentsQuery.mockImplementation((_: unknown, options: { selectFromResult: (result: unknown) => unknown }) =>
      options.selectFromResult({
        currentData: [
          { node_id: 1, user_id: 12, role_ids: [99] },
          { node_id: 5, user_id: 12, role_ids: [7] },
        ],
      })
    );
  });

  test("identifies the user and saves only the current node's assignments", () => {
    render(<UserToRoleUpdate />);

    expect(screen.getByRole("heading", { level: 1 }).textContent).toContain("Alex");
    expect(screen.getByRole("heading", { level: 1 }).textContent).toContain("Bar");
    expect(screen.getByText("userToRole.localRoles: Bar")).toBeTruthy();
    expect(screen.getByText("userToRole.inheritedRoles")).toBeTruthy();
    expect(screen.getByText("userToRole.localRolesHelp")).toBeTruthy();
    expect(screen.getByText("userToRole.inheritedFrom: Orga, Event")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "save" }));
    expect(mockUpdate).toHaveBeenCalledWith({ nodeId: 5, newUserToRoles: { user_id: 12, role_ids: [7] } });
    expect(screen.getByText("/node/5/users/12")).toBeTruthy();
  });

  test("starts with no local roles when the user has inherited roles only", () => {
    mockAssignmentsQuery.mockImplementation((_: unknown, options: { selectFromResult: (result: unknown) => unknown }) =>
      options.selectFromResult({ currentData: [{ node_id: 1, user_id: 12, role_ids: [99] }] })
    );
    render(<UserToRoleUpdate />);
    fireEvent.click(screen.getByRole("button", { name: "save" }));
    expect(mockUpdate).toHaveBeenCalledWith({ nodeId: 5, newUserToRoles: { user_id: 12, role_ids: [] } });
  });

  test("shows a load error instead of an endless loading indicator", () => {
    mockUserQuery.mockReturnValue({ error: { status: 404 } });
    render(<UserToRoleUpdate />);
    expect(screen.getByRole("alert").textContent).toBe("common.loadingError");
    expect(screen.queryByText("loading")).toBeNull();
  });

  test("waits for the new node's assignments instead of editing stale data after a node switch", () => {
    const { rerender } = render(<UserToRoleUpdate />);
    mockCurrentNode.id = 6;
    mockAssignmentsQuery.mockImplementation((_: unknown, options: { selectFromResult: (result: unknown) => unknown }) =>
      options.selectFromResult({ data: [{ node_id: 5, user_id: 12, role_ids: [7] }], currentData: undefined })
    );
    rerender(<UserToRoleUpdate />);
    expect(screen.getByText("loading")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "save" })).toBeNull();
  });

  test("initializes the form with the new node's roles even if that node is already cached", () => {
    const { rerender } = render(<UserToRoleUpdate />);
    mockCurrentNode.id = 6;
    mockAssignmentsQuery.mockImplementation((_: unknown, options: { selectFromResult: (result: unknown) => unknown }) =>
      options.selectFromResult({ currentData: [{ node_id: 6, user_id: 12, role_ids: [8] }] })
    );
    rerender(<UserToRoleUpdate />);
    fireEvent.click(screen.getByRole("button", { name: "save" }));
    expect(mockUpdate).toHaveBeenCalledWith({ nodeId: 6, newUserToRoles: { user_id: 12, role_ids: [8] } });
  });
});
