import { act, fireEvent, render, screen } from "@testing-library/react";
import { TextDecoder, TextEncoder } from "util";
import { Folder } from "@mui/icons-material";
import { SimpleTreeView } from "@mui/x-tree-view";
Object.assign(globalThis, { TextEncoder, TextDecoder });
const { MemoryRouter, useLocation } = require("react-router-dom");
const { NavigationTreeItem } = require("./NavigationTreeItem");
const Location = () => <span data-testid="location">{useLocation().pathname}</span>;
test("Enter activates tree items and their links while arrows move focus", () => {
  render(
    <MemoryRouter initialEntries={["/"]}>
      <Location />
      <SimpleTreeView defaultExpandedItems={["parent"]}>
        <NavigationTreeItem itemId="parent" to="/parent" labelText="Parent" labelIcon={Folder}>
          <NavigationTreeItem itemId="child" to="/child" labelText="Child" labelIcon={Folder} />
        </NavigationTreeItem>
      </SimpleTreeView>
    </MemoryRouter>
  );
  const parent = screen.getByRole("treeitem", { name: /Parent/ });
  const child = screen.getByRole("treeitem", { name: "Child", exact: true });
  act(() => parent.focus());
  fireEvent.keyDown(parent, { key: "ArrowDown" });
  expect(document.activeElement).toBe(child);
  fireEvent.keyDown(child, { key: "Enter" });
  expect(screen.getByTestId("location").textContent).toBe("/child");
  act(() => parent.focus());
  fireEvent.keyDown(parent, { key: "Enter" });
  expect(screen.getByTestId("location").textContent).toBe("/parent");
  expect(parent.getAttribute("aria-expanded")).toBe("true");
  const childLink = screen.getByRole("link", { name: "Child" });
  act(() => childLink.focus());
  fireEvent.keyDown(childLink, { key: "Enter" });
  expect(screen.getByTestId("location").textContent).toBe("/child");
  expect(parent.getAttribute("aria-expanded")).toBe("true");
});
