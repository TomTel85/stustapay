import { fireEvent, render, screen } from "@testing-library/react";
import { TextDecoder, TextEncoder } from "util";
Object.assign(globalThis, { TextEncoder, TextDecoder });
const mockTree = {
  id: 1,
  name: "Root",
  parent_ids: [],
  computed_forbidden_objects_at_node: [],
  children: [{ id: 10, name: "Child", parent_ids: [1], children: [], computed_forbidden_objects_at_node: [] }],
};
const mockDispatch = jest.fn();
jest.mock("@/api/nodes", () => ({
  useTreeForCurrentUser: () => mockTree,
  findNode: (id: number, node: typeof mockTree) =>
    id === node.id ? node : node.children.find((child) => child.id === id),
}));
jest.mock("@/store", () => ({
  selectExpandedNodes: "expanded",
  useAppSelector: () => ["/node/1", "/node/10"],
  useAppDispatch: () => mockDispatch,
  setSelectedNodes: (value: unknown) => ({ type: "selected", value }),
  setExpandedNodes: (value: unknown) => ({ type: "expanded", value }),
  extendExpandedNodes: (value: unknown) => ({ type: "extend", value }),
}));
jest.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
jest.mock("./NodeMenu", () => {
  const { Link, useLocation } = require("react-router-dom");
  return {
    nodeMenuEntryDefinitions: [{ route: (node: { id: number }) => `/node/${node.id}/users` }],
    isMenuEntryValidAtNode: () => true,
    NodeMenu: ({ node }: { node: { id: number } }) => {
      const { pathname } = useLocation();
      const route = `/node/${node.id}/users`;
      return (
        <Link to={route} aria-current={pathname === route || pathname.startsWith(`${route}/`) ? "page" : undefined}>
          Users {node.id}
        </Link>
      );
    },
  };
});
const { MemoryRouter, Link } = require("react-router-dom");
const { NavigationTree } = require("./NavigationTree");
test("selection follows routes, respects node boundaries and clears for unavailable routes", () => {
  render(
    <MemoryRouter initialEntries={["/node/1/users/details"]}>
      <Link to="/node/10/users">child users</Link>
      <Link to="/node/10">child</Link>
      <Link to="/node/999">unavailable</Link>
      <Link to="/help">help</Link>
      <NavigationTree />
    </MemoryRouter>
  );
  const selected = () =>
    Array.from(document.querySelectorAll(".MuiTreeItem-content.Mui-selected > .MuiTreeItem-label a")).map(
      (item) => item.textContent
    );
  expect(selected()).toEqual(["Root"]);
  expect(screen.getByRole("link", { name: "Users 1" }).getAttribute("aria-current")).toBe("page");
  fireEvent.click(screen.getByRole("link", { name: "child users" }));
  expect(selected()).toEqual(["Child"]);
  expect(screen.getByRole("link", { name: "Users 10" }).getAttribute("aria-current")).toBe("page");
  fireEvent.click(screen.getByRole("link", { name: "child" }));
  expect(selected()).toEqual(["Child"]);
  fireEvent.click(screen.getByRole("link", { name: "unavailable" }));
  expect(selected()).toEqual([]);
  expect(screen.queryByText("Users 10")).toBeNull();
  fireEvent.click(screen.getByRole("link", { name: "help" }));
  expect(selected()).toEqual([]);
});
