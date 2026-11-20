import * as React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { TextDecoder, TextEncoder } from "util";

Object.assign(globalThis, { TextEncoder, TextDecoder });

let mockCanManage = false;

jest.mock("@/api", () => ({
  useListUserToRoleQuery: () => ({
    currentData: [
      { user_id: 1, node_id: 5, role_ids: [7] },
      { user_id: 2, node_id: 1, role_ids: [8, 999] },
    ],
  }),
  useListUsersQuery: () => ({
    currentData: {
      entities: {
        1: { id: 1, node_id: 5, login: "zoe", display_name: "Zoe" },
        2: { id: 2, node_id: 1, login: "alex", display_name: "Alex" },
      },
    },
  }),
  useListUserRolesQuery: () => ({
    currentData: {
      entities: {
        7: { id: 7, node_id: 1, name: "Kassierer" },
        8: { id: 8, node_id: 1, name: "Schichtleitung" },
      },
    },
  }),
  selectUserById: (data: { entities: Record<number, unknown> }, id: number) => data.entities[id],
  selectUserRoleById: (data: { entities: Record<number, unknown> }, id: number) => data.entities[id],
  useGetUserQuery: () => ({}),
  useUpdateUserToRolesMutation: () => [jest.fn()],
  useNodeTree: () => ({ root: {} }),
  findNode: (id: number) => ({ name: id === 1 ? "Event" : "Bar" }),
}));
jest.mock("@/hooks", () => ({
  useCurrentNode: () => ({ currentNode: { id: 5 } }),
  useCurrentUserHasPrivilege: () => mockCanManage,
  useRenderNode: () => ({ dataGridNodeColumn: { field: "node_id" } }),
}));
jest.mock("@/components", () => ({
  ListLayout: ({
    children,
    additionalActions,
  }: {
    children: React.ReactNode;
    additionalActions: { label: string; onClick: () => void }[];
  }) => (
    <div>
      {additionalActions.map(({ label, onClick }) => (
        <button key={label} onClick={onClick}>
          {label}
        </button>
      ))}
      {children}
    </div>
  ),
}));
jest.mock("@stustapay/modal-provider", () => ({ useOpenModal: () => jest.fn() }));
jest.mock("react-i18next", () => ({
  useTranslation: () => ({
    i18n: { resolvedLanguage: "en" },
    t: (key: string, values?: { node?: string }) => (values?.node ? `${key}: ${values.node}` : key),
  }),
}));

const { MemoryRouter } = require("react-router-dom");
const { UserToRoleList } = require("./UserToRoleList");

test("sorts by displayed user name and searches role names", async () => {
  render(
    <MemoryRouter>
      <UserToRoleList />
    </MemoryRouter>
  );
  const links = screen.getAllByRole("link").filter((link) => /Alex|Zoe/.test(link.textContent ?? ""));
  expect(links.map((link) => link.textContent)).toEqual(["Alex (alex)", "Zoe (zoe)"]);
  expect(screen.getByText("userToRole.inheritedAt: Event")).toBeTruthy();
  expect(screen.getByText("#999")).toBeTruthy();
  expect(screen.getByRole("link", { name: "Schichtleitung" }).getAttribute("href")).toBe("/node/1/users/roles/8");
  expect(screen.queryByRole("button", { name: "user.assignRoles" })).toBeNull();

  fireEvent.change(screen.getByRole("searchbox"), { target: { value: "Kassierer" } });
  await waitFor(() => expect(screen.queryByRole("link", { name: "Alex (alex)" })).toBeNull());
  expect(screen.getByRole("link", { name: "Zoe (zoe)" })).toBeTruthy();
});

test("offers assignment and removal controls only where roles can be changed", () => {
  mockCanManage = true;
  render(
    <MemoryRouter>
      <UserToRoleList />
    </MemoryRouter>
  );

  expect(screen.getByRole("button", { name: "user.assignRoles" })).toBeTruthy();
  expect(
    screen.getByRole("row", { name: /Zoe/ }).querySelector('[aria-label="userToRole.deleteAssociation"]')
  ).toBeTruthy();
  expect(
    screen.getByRole("row", { name: /Alex/ }).querySelector('[aria-label="userToRole.deleteAssociation"]')
  ).toBeNull();
});
