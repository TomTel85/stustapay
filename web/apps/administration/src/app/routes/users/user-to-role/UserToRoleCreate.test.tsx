import * as React from "react";
import { fireEvent, render, screen } from "@testing-library/react";

const mockCreateMutation = jest.fn();
const mockUseUserRoleAssignments = jest.fn();
const mockReact = jest.requireActual("react") as typeof React;

jest.mock("@/api", () => ({ useUpdateUserToRolesMutation: () => [mockCreateMutation] }));
jest.mock("@/app/routes", () => ({ UserToRoleRoutes: { privilege: "manage", list: () => "/user-to-roles" } }));
jest.mock("@/app/layout", () => ({ withPrivilegeGuard: (_privilege: unknown, component: unknown) => component }));
jest.mock("@/hooks", () => ({ useCurrentNode: () => ({ currentNode: { id: 5, name: "Current" } }) }));
jest.mock("../roleAssignments", () => ({
  ...jest.requireActual("../roleAssignments"),
  useUserRoleAssignments: (...args: unknown[]) => mockUseUserRoleAssignments(...args),
}));
jest.mock("@/components/features", () => ({
  UserSelect: ({ label, onChange }: { label: string; onChange: (id: number) => void }) => (
    <button onClick={() => onChange(10)}>{label}</button>
  ),
  RoleSelect: ({ label, value }: { label: string; value: number[] }) => <div>{`${label}: ${value.join(",")}`}</div>,
}));
jest.mock("@/components", () => ({
  CreateLayout: ({
    initialValues,
    form: Form,
  }: {
    initialValues: { user_id: number; role_ids: number[] };
    form: React.ComponentType<Record<string, unknown>>;
  }) => {
    const [values, setValues] = mockReact.useState(initialValues);
    return (
      <Form
        values={values}
        errors={{}}
        touched={{}}
        setFieldValue={(field: "user_id" | "role_ids", value: number | number[]) =>
          setValues((old) => ({ ...old, [field]: value }))
        }
      />
    );
  },
}));
jest.mock("@stustapay/components", () => ({ Loading: () => <div>loading</div> }));
jest.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, values?: { role: string; node: string }) =>
      key === "userToRole.inheritedFrom" ? `${values?.role} (from ${values?.node})` : key,
  }),
}));

const { UserToRoleCreate } = require("./UserToRoleCreate") as typeof import("./UserToRoleCreate");

describe("UserToRoleCreate", () => {
  beforeEach(() => {
    mockCreateMutation.mockReset();
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

  test("preloads local IDs and keeps inherited roles read-only when selecting a user", () => {
    render(<UserToRoleCreate />);
    fireEvent.click(screen.getByRole("button", { name: "user.user" }));

    expect(screen.getByText("userToRole.localRoles: 2")).toBeTruthy();
    expect(screen.getByText("userToRole.inheritedRoles")).toBeTruthy();
    expect(screen.getByText("Inherited (from Root)")).toBeTruthy();
  });
});
