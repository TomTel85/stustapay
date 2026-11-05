import * as React from "react";
import { render, screen } from "@testing-library/react";
import { TextDecoder, TextEncoder } from "util";

(globalThis as typeof globalThis & { TextEncoder: typeof TextEncoder; TextDecoder: typeof TextDecoder }).TextEncoder =
  TextEncoder;
(globalThis as typeof globalThis & { TextEncoder: typeof TextEncoder; TextDecoder: typeof TextDecoder }).TextDecoder =
  TextDecoder;

const mockUseNode = jest.fn();

jest.mock("@/api/nodes", () => ({
  useNode: (...args: unknown[]) => mockUseNode(...args),
}));

jest.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

const { MemoryRouter, Route, Routes } = require("react-router-dom");
const { UserPageLayout } = require("./UserPageLayout");

describe("UserPageLayout", () => {
  const node = {
    id: 5,
    event: {},
    privileges_at_node: ["node_administration"],
    computed_forbidden_objects_at_node: [],
  };

  const renderAt = (path: string) =>
    render(
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/node/:nodeId/*" element={<UserPageLayout />}>
            <Route path="users/*" element={<div>users page</div>} />
            <Route path="user-to-roles/*" element={<div>assignments page</div>} />
            <Route path="cashiers/*" element={<div>cashiers page</div>} />
          </Route>
        </Routes>
      </MemoryRouter>
    );

  beforeEach(() => {
    mockUseNode.mockReset();
    mockUseNode.mockReturnValue({ node });
  });

  test.each([
    ["/node/5/users", "user.users"],
    ["/node/5/user-to-roles", "userToRoles"],
    ["/node/5/user-to-roles/12/edit", "userToRoles"],
    ["/node/5/cashiers", "cashiers"],
    ["/node/5/cashiers/12/close-out", "cashiers"],
    ["/node/5/cashiers/12/shifts/34", "cashiers"],
  ])("renders tabs and selects the matching tab at %s", (path, selectedTab) => {
    renderAt(path);

    expect(screen.getByRole("tab", { name: "user.users" }).getAttribute("href")).toBe("/node/5/users");
    expect(screen.getByRole("tab", { name: "user.roles" }).getAttribute("href")).toBe("/node/5/users/roles");
    expect(screen.getByRole("tab", { name: "userToRoles" }).getAttribute("href")).toBe("/node/5/user-to-roles");
    expect(screen.getByRole("tab", { name: "cashiers" }).getAttribute("href")).toBe("/node/5/cashiers");
    expect(screen.getByRole("tab", { name: selectedTab }).getAttribute("aria-selected")).toBe("true");
  });

  test.each([
    { event: null },
    { privileges_at_node: ["user_management"] },
    { computed_forbidden_objects_at_node: ["user", "user_role"] },
  ])("hides cashiers when the previous menu requirements are not met: %o", (overrides) => {
    mockUseNode.mockReturnValue({ node: { ...node, ...overrides } });
    renderAt("/node/5/users");
    expect(screen.queryByRole("tab", { name: "cashiers" })).toBeNull();
  });

  test("hides the roles tab when user roles are forbidden, while keeping assignments available", () => {
    mockUseNode.mockReturnValue({ node: { ...node, computed_forbidden_objects_at_node: ["user_role"] } });

    renderAt("/node/5/user-to-roles");

    expect(screen.queryByRole("tab", { name: "user.roles" })).toBeNull();
    expect(screen.getByRole("tab", { name: "user.users" })).toBeTruthy();
    expect(screen.getByRole("tab", { name: "userToRoles" }).getAttribute("aria-selected")).toBe("true");
  });
});
