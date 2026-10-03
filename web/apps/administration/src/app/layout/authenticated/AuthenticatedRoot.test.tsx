import { fireEvent, render, screen } from "@testing-library/react";
import { TextDecoder, TextEncoder } from "util";

(globalThis as typeof globalThis & { TextEncoder: typeof TextEncoder; TextDecoder: typeof TextDecoder }).TextEncoder =
  TextEncoder;
(globalThis as typeof globalThis & { TextEncoder: typeof TextEncoder; TextDecoder: typeof TextDecoder }).TextDecoder =
  TextDecoder;

jest.mock("@/api", () => ({
  useGetProfileQuery: () => ({
    data: null,
  }),
  useGetTreeForCurrentUserQuery: () => ({
    data: {
      id: 1,
      name: "Festival",
      parent_ids: [],
      children: [
        {
          id: 42,
          name: "Bar 1",
          parent_ids: [1],
          children: [],
        },
      ],
    },
    isLoading: false,
    error: null,
  }),
  useLogoutMutation: () => [
    () => ({
      unwrap: () => Promise.resolve(),
    }),
  ],
}));

jest.mock("@/api/common", () => ({
  config: {
    testMode: false,
    testModeMessage: "",
  },
}));

jest.mock("@/components", () => {
  const React = require("react");

  return {
    AppBar: ({ children }: { children: unknown }) => <div>{children}</div>,
    DrawerHeader: () => <div data-testid="drawer-header" />,
    Main: ({ children }: { children: unknown }) => <main>{children}</main>,
    LanguageSelect: () => <div data-testid="language-select" />,
  };
});

jest.mock("@/store", () => ({
  selectCurrentUser: "selectCurrentUser",
  useAppDispatch: () => jest.fn(),
  useAppSelector: () => ({
    login: "admin",
  }),
}));

jest.mock("@stustapay/components", () => ({
  Loading: () => <div>loading</div>,
  TestModeDisclaimer: () => null,
}));

jest.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

jest.mock("./navigation-tree", () => ({
  NavigationTree: () => <div>navigation-tree</div>,
}));

const { MemoryRouter, Route, Routes } = require("react-router-dom");
const { AuthenticatedRoot } = require("./AuthenticatedRoot");

describe("AuthenticatedRoot", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  beforeAll(() => {
    Object.defineProperty(window, "matchMedia", {
      writable: true,
      value: jest.fn().mockImplementation((query: string) => ({
        matches: false,
        media: query,
        onchange: null,
        addListener: jest.fn(),
        removeListener: jest.fn(),
        addEventListener: jest.fn(),
        removeEventListener: jest.fn(),
        dispatchEvent: jest.fn(),
      })),
    });
  });

  test("renders a help shortcut that preserves the current node context", () => {
    render(
      <MemoryRouter initialEntries={["/node/42/products"]}>
        <Routes>
          <Route element={<AuthenticatedRoot />}>
            <Route path="*" element={<div>Outlet</div>} />
          </Route>
        </Routes>
      </MemoryRouter>
    );

    expect(screen.getByRole("link", { name: "help.open" }).getAttribute("href")).toBe("/help?nodeId=42");
  });

  test("renders the current node path in the header", () => {
    render(
      <MemoryRouter initialEntries={["/node/42/products"]}>
        <Routes>
          <Route element={<AuthenticatedRoot />}>
            <Route path="*" element={<div>Outlet</div>} />
          </Route>
        </Routes>
      </MemoryRouter>
    );

    expect(screen.getByText("TeamFestlichPay")).toBeTruthy();
    expect(screen.getByText("Festival > Bar 1")).toBeTruthy();
    expect(screen.getByRole("link", { name: "auth.profile" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "logout" })).toBeTruthy();
  });

  const renderLayout = () => render(
    <MemoryRouter initialEntries={["/node/42/products"]}>
      <Routes>
        <Route element={<AuthenticatedRoot />}>
          <Route path="*" element={<div>Outlet</div>} />
        </Route>
      </Routes>
    </MemoryRouter>
  );

  test("resizes by keyboard, limits the width, and restores the saved preference", () => {
    const view = renderLayout();
    const handle = screen.getByRole("separator", { name: "auth.resizeSidebar" });
    fireEvent.keyDown(handle, { key: "ArrowRight", shiftKey: true });
    expect(handle.getAttribute("aria-valuenow")).toBe("330");
    expect(window.localStorage.getItem("administration.sidebarWidth")).toBe("330");
    view.unmount();
    renderLayout();
    const restored = screen.getByRole("separator", { name: "auth.resizeSidebar" });
    expect(restored.getAttribute("aria-valuenow")).toBe("330");
    fireEvent.keyDown(restored, { key: "Home" });
    fireEvent.keyDown(restored, { key: "ArrowLeft" });
    expect(restored.getAttribute("aria-valuenow")).toBe("220");
    fireEvent.keyDown(restored, { key: "End" });
    fireEvent.keyDown(restored, { key: "ArrowRight" });
    expect(restored.getAttribute("aria-valuenow")).toBe(restored.getAttribute("aria-valuemax"));
    fireEvent.doubleClick(restored);
    expect(restored.getAttribute("aria-valuenow")).toBe("280");
  });

  test("drags the sidebar edge and stops resizing when pointer capture is lost", () => {
    // JSDOM does not implement pointer events or pointer capture.
    window.PointerEvent = MouseEvent as typeof PointerEvent;
    renderLayout();
    const handle = screen.getByRole("separator", { name: "auth.resizeSidebar" });
    handle.setPointerCapture = jest.fn();
    fireEvent.pointerDown(handle, { button: 0, clientX: 280 });
    fireEvent.pointerMove(handle, { clientX: 380 });
    expect(handle.getAttribute("aria-valuenow")).toBe("380");
    fireEvent.lostPointerCapture(handle);
    fireEvent.pointerMove(handle, { clientX: 480 });
    expect(handle.getAttribute("aria-valuenow")).toBe("380");
  });

  test("keeps the fixed mobile sidebar without a resize handle", () => {
    const matchMedia = jest.spyOn(window, "matchMedia");
    matchMedia.mockImplementation((query: string) => ({
      matches: true,
      media: query,
      onchange: null,
      addListener: jest.fn(),
      removeListener: jest.fn(),
      addEventListener: jest.fn(),
      removeEventListener: jest.fn(),
      dispatchEvent: jest.fn(),
    }));
    renderLayout();
    fireEvent.click(screen.getByRole("button", { name: "open drawer" }));
    expect(screen.queryByRole("separator", { name: "auth.resizeSidebar" })).toBeNull();
    matchMedia.mockRestore();
  });
});
