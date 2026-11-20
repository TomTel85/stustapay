import * as React from "react";
import { render, screen } from "@testing-library/react";
import { TextDecoder, TextEncoder } from "util";

(globalThis as typeof globalThis & { TextEncoder: typeof TextEncoder; TextDecoder: typeof TextDecoder }).TextEncoder =
  TextEncoder;
(globalThis as typeof globalThis & { TextEncoder: typeof TextEncoder; TextDecoder: typeof TextDecoder }).TextDecoder =
  TextDecoder;

const mockUseNode = jest.fn();
jest.mock("@/api", () => ({ useNode: (...args: unknown[]) => mockUseNode(...args) }));
jest.mock("@/api/nodes", () => ({ useTreeForCurrentUser: () => ({ id: 42 }) }));
jest.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
jest.mock("./EventPageLayout", () => ({ EventPageLayout: () => <div>Event layout</div> }));

const { MemoryRouter, Route, Routes } = require("react-router-dom");
const { NodePageLayout } = require("./NodePageLayout");

describe("NodePageLayout", () => {
  test.each(["/node/999", "/node/invalid"])("shows a recovery link for unavailable workspace %s", (path) => {
    mockUseNode.mockReturnValue({ node: undefined });
    render(
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/node/:nodeId" element={<NodePageLayout />}>
            <Route index element={<div>Protected content</div>} />
          </Route>
        </Routes>
      </MemoryRouter>
    );
    expect(screen.getByText("nodes.unavailableTitle")).toBeTruthy();
    expect(screen.getByRole("link", { name: "nodes.returnToWorkspace" }).getAttribute("href")).toBe("/node/42");
    expect(screen.queryByText("Protected content")).toBeNull();
  });

  test("renders the valid workspace content", () => {
    mockUseNode.mockReturnValue({ node: { id: 42, event: null } });
    render(
      <MemoryRouter initialEntries={["/node/42"]}>
        <Routes>
          <Route path="/node/:nodeId" element={<NodePageLayout />}>
            <Route index element={<div>Workspace content</div>} />
          </Route>
        </Routes>
      </MemoryRouter>
    );
    expect(screen.getByText("Workspace content")).toBeTruthy();
    expect(screen.getByRole("tablist", { name: "portal.workspace" })).toBeTruthy();
  });
});
