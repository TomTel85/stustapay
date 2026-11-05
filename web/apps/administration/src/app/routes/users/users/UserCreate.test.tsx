import * as React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

const mockNavigate = jest.fn();
const mockCreateUser = jest.fn();
jest.mock("react-router-dom", () => ({ useNavigate: () => mockNavigate }));
jest.mock("@/api", () => ({ useCreateUserMutation: () => [mockCreateUser] }));
jest.mock("@/hooks", () => ({ useCurrentNode: () => ({ currentNode: { id: 5 } }) }));
jest.mock("@/app/layout", () => ({ withPrivilegeGuard: (_: string, component: unknown) => component }));
jest.mock("@/components", () => ({ CreateLayout: require("@/components/layouts/CreateLayout").CreateLayout }));
jest.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
jest.mock("./UserCreateForm", () => ({
  UserCreateForm: (props: { setFieldValue: (field: string, value: string) => void }) => (
    <input
      aria-label="login"
      onChange={(event) => {
        props.setFieldValue("login", event.target.value);
        props.setFieldValue("display_name", event.target.value);
      }}
    />
  ),
}));

const { UserCreate } = require("./UserCreate");

beforeEach(() => {
  jest.clearAllMocks();
  mockCreateUser.mockReturnValue({ unwrap: () => Promise.resolve({ id: 12 }) });
});

function setup() {
  render(<UserCreate />);
  fireEvent.change(screen.getByLabelText("login"), { target: { value: "alex" } });
}

test("creates a user and opens role assignment at the current node", async () => {
  setup();
  fireEvent.click(screen.getByRole("button", { name: "user.createAndAssignRoles" }));
  await waitFor(() => expect(mockNavigate).toHaveBeenCalledWith("/node/5/user-to-roles/12/edit"));
  expect(mockCreateUser).toHaveBeenCalledWith(expect.objectContaining({ nodeId: 5 }));
  expect(mockNavigate).toHaveBeenCalledTimes(1);
});

test("normal creation returns to the user list", async () => {
  setup();
  fireEvent.click(screen.getByRole("button", { name: "add" }));
  await waitFor(() => expect(mockNavigate).toHaveBeenCalledWith("/node/5/users"));
});

test("does not navigate when creation fails", async () => {
  const warning = jest.spyOn(console, "warn").mockImplementation(() => undefined);
  mockCreateUser.mockReturnValue({ unwrap: () => Promise.reject(new Error("Unavailable")) });
  setup();
  fireEvent.click(screen.getByRole("button", { name: "user.createAndAssignRoles" }));
  await waitFor(() => expect(warning).toHaveBeenCalled());
  expect(mockNavigate).not.toHaveBeenCalled();
  warning.mockRestore();
});
